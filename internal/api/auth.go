package api

import (
	"log"
	"math/rand"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
	"github.com/plasma/fh-mahjong/internal/storage"
	"golang.org/x/crypto/bcrypt"
	"gorm.io/gorm"
)

// AuthHandler groups the DB dependency
type AuthHandler struct {
	DB *gorm.DB
}

type RegisterRequest struct {
	Email       string `json:"email" binding:"required,email"`
	Password    string `json:"password" binding:"required,min=8"`
	DisplayName string `json:"displayName" binding:"required,min=2,max=30"`
}

type LoginRequest struct {
	Email    string `json:"email" binding:"required,email"`
	Password string `json:"password" binding:"required"`
}

type AuthResponse struct {
	Token string      `json:"token"`
	User  storage.User `json:"user"`
}

var jwtSecret = []byte(getEnv("JWT_SECRET", "super-secret-key-change-in-prod"))

// dummyPasswordHash equalizes the timing of the unknown-email login path with
// the wrong-password path: on a lookup miss we still run one bcrypt comparison
// against this fixed hash, so an attacker cannot distinguish registered emails
// by response latency. Computed once at startup at the same cost as real hashes.
var dummyPasswordHash, _ = bcrypt.GenerateFromPassword([]byte("fh-login-timing-equalizer"), bcrypt.DefaultCost)

func getEnv(key, fallback string) string {
	if value, ok := os.LookupEnv(key); ok {
		return value
	}
	return fallback
}

func normalizeEmail(s string) string {
	return strings.ToLower(strings.TrimSpace(s))
}

// issueToken builds a signed HS256 JWT carrying the user id (sub), display name
// (username) and an expiry. Used by Login, Register, GuestLogin and UpdateMe.
func issueToken(id uint, username string, ttl time.Duration) (string, error) {
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
		"sub":      id,
		"username": username,
		"exp":      time.Now().Add(ttl).Unix(),
	})
	return token.SignedString(jwtSecret)
}

// Register creates an account keyed by email and auto-logs the user in.
func (h *AuthHandler) Register(c *gin.Context) {
	var req RegisterRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	if h.DB == nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{"error": "Database is temporarily disabled. Please use 'Guest Login'."})
		return
	}

	email := normalizeEmail(req.Email)

	var existing storage.User
	if err := h.DB.Where("email = ?", email).First(&existing).Error; err == nil {
		c.JSON(http.StatusConflict, gin.H{"error": "Email already registered"})
		return
	}

	hashed, err := bcrypt.GenerateFromPassword([]byte(req.Password), bcrypt.DefaultCost)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to hash password"})
		return
	}

	user := storage.User{
		Email:        email,
		Username:     req.DisplayName,
		PasswordHash: string(hashed),
		Rating:       1500,
	}

	// Random ids can (astronomically rarely) collide on the PK; retry a few times,
	// zeroing the id so BeforeCreate regenerates it.
	var createErr error
	for attempt := 0; attempt < 5; attempt++ {
		user.ID = 0
		createErr = h.DB.Create(&user).Error
		if createErr == nil {
			break
		}
	}
	if createErr != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to create user"})
		return
	}

	token, err := issueToken(user.ID, user.Username, 72*time.Hour)
	if err != nil {
		log.Printf("Failed to sign token: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to generate token"})
		return
	}

	user.PasswordHash = ""
	c.JSON(http.StatusCreated, AuthResponse{Token: token, User: user})
}

// Login authenticates by email + password and returns a JWT.
func (h *AuthHandler) Login(c *gin.Context) {
	var req LoginRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	if h.DB == nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{"error": "Database is temporarily disabled. Please use 'Guest Login'."})
		return
	}

	email := normalizeEmail(req.Email)

	var user storage.User
	if err := h.DB.Where("email = ?", email).First(&user).Error; err != nil {
		// Equalize timing with the wrong-password path so the unknown-email
		// case can't be distinguished by latency (anti-enumeration).
		bcrypt.CompareHashAndPassword(dummyPasswordHash, []byte(req.Password))
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Invalid email or password"})
		return
	}
	if err := bcrypt.CompareHashAndPassword([]byte(user.PasswordHash), []byte(req.Password)); err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Invalid email or password"})
		return
	}

	token, err := issueToken(user.ID, user.Username, 72*time.Hour)
	if err != nil {
		log.Printf("Failed to sign token: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to generate token"})
		return
	}

	user.PasswordHash = ""
	c.JSON(http.StatusOK, AuthResponse{Token: token, User: user})
}

type UpdateProfileRequest struct {
	Email       *string `json:"email" binding:"omitempty,email"`
	DisplayName *string `json:"displayName" binding:"omitempty,min=2,max=30"`
}

// UpdateMe lets an authenticated account change its email and/or display name.
// A fresh token is always returned so the `username` claim stays current.
func (h *AuthHandler) UpdateMe(c *gin.Context) {
	var req UpdateProfileRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	if h.DB == nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{"error": "Database is temporarily disabled."})
		return
	}

	uid, _ := c.Get("userID")
	var user storage.User
	if err := h.DB.First(&user, uid).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "User not found"})
		return
	}

	if req.Email != nil {
		email := normalizeEmail(*req.Email)
		if email != user.Email {
			var other storage.User
			if err := h.DB.Where("email = ? AND id <> ?", email, user.ID).First(&other).Error; err == nil {
				c.JSON(http.StatusConflict, gin.H{"error": "Email already registered"})
				return
			}
			user.Email = email
		}
	}
	if req.DisplayName != nil {
		user.Username = *req.DisplayName
	}

	if err := h.DB.Save(&user).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to update profile"})
		return
	}

	token, err := issueToken(user.ID, user.Username, 72*time.Hour)
	if err != nil {
		log.Printf("Failed to sign token: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to generate token"})
		return
	}

	user.PasswordHash = ""
	c.JSON(http.StatusOK, AuthResponse{Token: token, User: user})
}

type GuestRequest struct {
	Username string `json:"username" binding:"required"`
}

func (h *AuthHandler) GuestLogin(c *gin.Context) {
	var req GuestRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// Generate a random temporary User ID (high number to avoid collision with standard DB IDs)
	rand.Seed(time.Now().UnixNano())
	tempUserID := uint(9000000 + rand.Intn(1000000))

	tokenString, err := issueToken(tempUserID, req.Username, 24*time.Hour)
	if err != nil {
		log.Printf("Failed to sign guest token: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to generate token"})
		return
	}

	// We return a mock user object to satisfy the frontend's expectations
	mockUser := storage.User{
		ID:       tempUserID,
		Username: req.Username,
		Rating:   1500,
	}

	c.JSON(http.StatusOK, AuthResponse{
		Token: tokenString,
		User:  mockUser,
	})
}
