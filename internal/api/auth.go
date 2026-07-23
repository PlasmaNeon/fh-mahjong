package api

import (
	"crypto/rand"
	"encoding/base64"
	"errors"
	"fmt"
	"net/http"
	netmail "net/mail"
	"os"
	"strings"
	"time"
	"unicode"
	"unicode/utf8"

	"github.com/gin-gonic/gin"
	"github.com/plasma/fh-mahjong/internal/mail"
	"github.com/plasma/fh-mahjong/internal/storage"
	"golang.org/x/crypto/bcrypt"
	"gorm.io/gorm"
)

const (
	sessionTTL            = 30 * 24 * time.Hour
	devSessionCookieName  = "fh_session"
	prodSessionCookieName = "__Host-fh_session"
)

// AuthHandler owns account creation, login, and password recovery. Mail and
// ResetLimiter are only used by the password-reset endpoints.
type AuthHandler struct {
	DB           *gorm.DB
	Mail         mail.Sender
	ResetLimiter *keyedRateLimiter
}

// RegisterRequest creates an account from a username and password only.
// Email is deliberately absent: it is an optional profile field set later
// through PATCH /users/me, never collected at signup. `displayName` remains
// as the legacy alias for `username`.
type RegisterRequest struct {
	Username    string `json:"username"`
	DisplayName string `json:"displayName"`
	Password    string `json:"password" binding:"required,min=8"`
}

type LoginRequest struct {
	Identifier string `json:"identifier"`
	Email      string `json:"email"`
	Password   string `json:"password" binding:"required"`
}

type AuthResponse struct {
	User      storage.User `json:"user"`
	CSRFToken string       `json:"csrfToken"`
}

var dummyPasswordHash, _ = bcrypt.GenerateFromPassword([]byte("fh-login-timing-equalizer"), bcrypt.DefaultCost)

func getEnv(key, fallback string) string {
	if value, ok := os.LookupEnv(key); ok {
		return value
	}
	return fallback
}

func normalizeEmail(value string) string {
	return strings.ToLower(strings.TrimSpace(value))
}

func resolveAlias(canonical, legacy, field string) (string, error) {
	canonical = strings.TrimSpace(canonical)
	legacy = strings.TrimSpace(legacy)
	if canonical != "" && legacy != "" && canonical != legacy {
		return "", fmt.Errorf("%s and legacy alias disagree", field)
	}
	if canonical != "" {
		return canonical, nil
	}
	return legacy, nil
}

func validateUsername(value string) (string, string, error) {
	if strings.Contains(value, "@") {
		return "", "", errors.New("username cannot contain @")
	}
	for _, r := range value {
		if !(unicode.IsLetter(r) || unicode.IsNumber(r) || unicode.IsSpace(r) || r == '_' || r == '-') {
			return "", "", errors.New("username may contain letters, numbers, spaces, _ and -")
		}
	}
	display, key := storage.NormalizeUsername(value)
	count := utf8.RuneCountInString(display)
	if count < 2 || count > 30 {
		return "", "", errors.New("username must be 2 to 30 characters")
	}
	return display, key, nil
}

func randomCredential() (string, error) {
	buf := make([]byte, 32)
	if _, err := rand.Read(buf); err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(buf), nil
}

func createSession(db *gorm.DB, userID uint) (string, storage.UserSession, error) {
	rawToken, err := randomCredential()
	if err != nil {
		return "", storage.UserSession{}, err
	}
	csrfToken, err := randomCredential()
	if err != nil {
		return "", storage.UserSession{}, err
	}
	session := storage.UserSession{
		TokenHash: hashSessionToken(rawToken),
		UserID:    userID,
		CSRFToken: csrfToken,
		ExpiresAt: time.Now().Add(sessionTTL),
	}
	if err := db.Create(&session).Error; err != nil {
		return "", storage.UserSession{}, err
	}
	// Keep the session table bounded without introducing another background
	// worker; this deletion is indexed and runs only when a new session starts.
	db.Where("expires_at <= ?", time.Now()).Delete(&storage.UserSession{})
	return rawToken, session, nil
}

// isProduction reports whether this process is running as a production
// deployment. It gates both Secure-cookie behaviour and anything else that
// must not behave like a development convenience in production.
func isProduction() bool {
	return strings.EqualFold(os.Getenv("APP_ENV"), "production") || strings.EqualFold(os.Getenv("GIN_MODE"), "release")
}

func isProductionCookie() bool {
	return isProduction()
}

func setSessionCookie(c *gin.Context, rawToken string) {
	production := isProductionCookie()
	name := devSessionCookieName
	if production {
		name = prodSessionCookieName
	}
	http.SetCookie(c.Writer, &http.Cookie{
		Name:     name,
		Value:    rawToken,
		Path:     "/",
		MaxAge:   int(sessionTTL.Seconds()),
		Expires:  time.Now().Add(sessionTTL),
		HttpOnly: true,
		Secure:   production,
		SameSite: http.SameSiteLaxMode,
	})
}

func clearSessionCookies(c *gin.Context) {
	for _, cookie := range []http.Cookie{
		{Name: prodSessionCookieName, Secure: true},
		{Name: devSessionCookieName, Secure: false},
	} {
		cookie.Value = ""
		cookie.Path = "/"
		cookie.MaxAge = -1
		cookie.Expires = time.Unix(1, 0)
		cookie.HttpOnly = true
		cookie.SameSite = http.SameSiteLaxMode
		http.SetCookie(c.Writer, &cookie)
	}
}

func isUniqueConstraintError(err error) bool {
	if err == nil {
		return false
	}
	message := strings.ToLower(err.Error())
	return strings.Contains(message, "unique constraint") || strings.Contains(message, "duplicate key")
}

func authResponse(user storage.User, csrfToken string) AuthResponse {
	user.PasswordHash = ""
	return AuthResponse{User: user, CSRFToken: csrfToken}
}

func (h *AuthHandler) Register(c *gin.Context) {
	var req RegisterRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		respondError(c, http.StatusBadRequest, err.Error())
		return
	}
	if h.DB == nil {
		respondError(c, http.StatusServiceUnavailable, "Database is temporarily disabled.")
		return
	}
	requestedName, err := resolveAlias(req.Username, req.DisplayName, "username")
	if err != nil {
		respondError(c, http.StatusBadRequest, err.Error())
		return
	}
	username, usernameKey, err := validateUsername(requestedName)
	if err != nil {
		respondError(c, http.StatusBadRequest, err.Error())
		return
	}
	hashedPassword, err := bcrypt.GenerateFromPassword([]byte(req.Password), bcrypt.DefaultCost)
	if err != nil {
		respondError(c, http.StatusInternalServerError, "Failed to hash password")
		return
	}
	user := storage.User{
		Username:     username,
		UsernameKey:  usernameKey,
		PasswordHash: string(hashedPassword),
		Rating:       1500,
	}
	var rawToken string
	var session storage.UserSession
	err = h.DB.Transaction(func(tx *gorm.DB) error {
		if err := tx.Create(&user).Error; err != nil {
			return err
		}
		var err error
		rawToken, session, err = createSession(tx, user.ID)
		return err
	})
	if err != nil {
		if isUniqueConstraintError(err) {
			respondError(c, http.StatusConflict, "Username is already registered")
			return
		}
		respondError(c, http.StatusInternalServerError, "Failed to create account")
		return
	}
	setSessionCookie(c, rawToken)
	c.Header("Cache-Control", "no-store")
	c.JSON(http.StatusCreated, authResponse(user, session.CSRFToken))
}

func (h *AuthHandler) Login(c *gin.Context) {
	var req LoginRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		respondError(c, http.StatusBadRequest, err.Error())
		return
	}
	if h.DB == nil {
		respondError(c, http.StatusServiceUnavailable, "Database is temporarily disabled.")
		return
	}
	identifier, err := resolveAlias(req.Identifier, req.Email, "identifier")
	if err != nil || identifier == "" {
		respondError(c, http.StatusBadRequest, "Username or email is required")
		return
	}

	user, found := lookupUserByIdentifier(h.DB, identifier)
	if !found {
		bcrypt.CompareHashAndPassword(dummyPasswordHash, []byte(req.Password))
		respondError(c, http.StatusUnauthorized, "Invalid username/email or password")
		return
	}
	if err := bcrypt.CompareHashAndPassword([]byte(user.PasswordHash), []byte(req.Password)); err != nil {
		respondError(c, http.StatusUnauthorized, "Invalid username/email or password")
		return
	}
	rawToken, session, err := createSession(h.DB, user.ID)
	if err != nil {
		respondError(c, http.StatusInternalServerError, "Failed to start session")
		return
	}
	setSessionCookie(c, rawToken)
	c.Header("Cache-Control", "no-store")
	c.JSON(http.StatusOK, authResponse(user, session.CSRFToken))
}

func (h *AuthHandler) Session(c *gin.Context) {
	user, ok := c.Get("authUser")
	if !ok {
		abortError(c, http.StatusUnauthorized, "Authentication required")
		return
	}
	csrf, _ := c.Get("csrfToken")
	c.Header("Cache-Control", "no-store")
	c.JSON(http.StatusOK, authResponse(user.(storage.User), csrf.(string)))
}

func (h *AuthHandler) Logout(c *gin.Context) {
	if h.DB != nil {
		if sessionID, ok := c.Get("sessionID"); ok {
			h.DB.Delete(&storage.UserSession{}, sessionID)
		}
	}
	clearSessionCookies(c)
	c.Status(http.StatusNoContent)
}

// UpdateProfileRequest carries an optional username and/or email change. For
// Email the three JSON states are distinct: key absent (or null) means "no
// change", a non-empty string sets or replaces the address, and "" clears it
// back to NULL.
//
// Email deliberately carries no `binding:"...email"` tag. go-playground's
// validator only treats a *string as empty (for `omitempty`) when the
// pointer itself is nil; a non-nil pointer to "" — exactly the clear
// request — still hits the `email` format check and gets rejected (verified
// against this repo's pinned validator v10.30.1). UpdateMe instead validates
// format by hand, and only when the normalized value is non-empty, so
// clearing is never subject to format validation. The hand-rolled check is
// deliberately stricter than a bare net/mail.ParseAddress call: ParseAddress
// alone accepts RFC 5322 display-name forms ("Rain <rain@example.com>") and
// quoted local parts, so it also requires the parsed address to have no
// display name, to equal the normalized input exactly, and the input to
// contain exactly one "@" — accepting only a bare addr-spec.
type UpdateProfileRequest struct {
	Email           *string `json:"email"`
	Username        *string `json:"username"`
	DisplayName     *string `json:"displayName"`
	CurrentPassword *string `json:"currentPassword"`
}

func (h *AuthHandler) UpdateMe(c *gin.Context) {
	var req UpdateProfileRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		respondError(c, http.StatusBadRequest, err.Error())
		return
	}
	if h.DB == nil {
		respondError(c, http.StatusServiceUnavailable, "Database is temporarily disabled.")
		return
	}
	uid, _ := c.Get("userID")
	var user storage.User
	if err := h.DB.First(&user, uid).Error; err != nil {
		respondError(c, http.StatusNotFound, "User not found")
		return
	}

	var requestedUsername string
	if req.Username != nil || req.DisplayName != nil {
		canonical, legacy := "", ""
		if req.Username != nil {
			canonical = *req.Username
		}
		if req.DisplayName != nil {
			legacy = *req.DisplayName
		}
		var err error
		requestedUsername, err = resolveAlias(canonical, legacy, "username")
		if err != nil {
			respondError(c, http.StatusBadRequest, err.Error())
			return
		}
	}
	// newEmail nil while emailChange is true means "clear it".
	var newEmail *string
	emailChange := false
	if req.Email != nil {
		normalized := normalizeEmail(*req.Email)
		switch {
		case normalized == "":
			emailChange = user.Email != nil
		case user.Email == nil || *user.Email != normalized:
			parsed, err := netmail.ParseAddress(normalized)
			if err != nil || parsed.Name != "" || parsed.Address != normalized || strings.Count(normalized, "@") != 1 {
				respondError(c, http.StatusBadRequest, "Invalid email address")
				return
			}
			emailChange = true
			newEmail = &normalized
		}
	}
	newUsername, newUsernameKey := user.Username, user.UsernameKey
	usernameChange := false
	if requestedUsername != "" {
		var err error
		newUsername, newUsernameKey, err = validateUsername(requestedUsername)
		if err != nil {
			respondError(c, http.StatusBadRequest, err.Error())
			return
		}
		usernameChange = newUsername != user.Username
	}
	if !emailChange && !usernameChange {
		respondError(c, http.StatusBadRequest, "No changes requested")
		return
	}
	if emailChange {
		if req.CurrentPassword == nil || *req.CurrentPassword == "" {
			respondError(c, http.StatusBadRequest, "Current password is required to change email")
			return
		}
		if err := bcrypt.CompareHashAndPassword([]byte(user.PasswordHash), []byte(*req.CurrentPassword)); err != nil {
			respondError(c, http.StatusUnauthorized, "Incorrect password")
			return
		}
	}
	updates := map[string]any{}
	if emailChange {
		if newEmail == nil {
			updates["email"] = nil
		} else {
			updates["email"] = *newEmail
		}
		// A newly set or cleared address is never a verified one.
		updates["email_verified_at"] = nil
	}
	if usernameChange {
		updates["username"] = newUsername
		updates["username_key"] = newUsernameKey
	}
	if err := h.DB.Transaction(func(tx *gorm.DB) error {
		if err := tx.Model(&user).Updates(updates).Error; err != nil {
			return err
		}
		if !emailChange {
			return nil
		}
		// Any code already in flight went to the OLD address. Changing or
		// clearing the address must retire it, or whoever still controls that
		// inbox can complete the reset the owner just acted to prevent.
		return tx.Model(&storage.PasswordResetCode{}).
			Where("user_id = ? AND consumed_at IS NULL", user.ID).
			Update("consumed_at", time.Now()).Error
	}); err != nil {
		if isUniqueConstraintError(err) {
			respondError(c, http.StatusConflict, "Email or username is already registered")
			return
		}
		respondError(c, http.StatusInternalServerError, "Failed to update profile")
		return
	}
	if err := h.DB.First(&user, user.ID).Error; err != nil {
		respondError(c, http.StatusInternalServerError, "Failed to reload profile")
		return
	}
	csrf, _ := c.Get("csrfToken")
	c.JSON(http.StatusOK, authResponse(user, csrf.(string)))
}
