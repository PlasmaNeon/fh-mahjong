package api

import (
	"context"
	"crypto/rand"
	"fmt"
	"log"
	"math/big"
	"net/http"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/plasma/fh-mahjong/internal/storage"
	"golang.org/x/crypto/bcrypt"
	"gorm.io/gorm"
)

const (
	// A code is short-lived on purpose: it is the only thing standing between
	// an inbox and an account, and the short window also keeps a leaked
	// database of bcrypt-hashed codes worthless before it could be cracked.
	passwordResetCodeTTL     = 15 * time.Minute
	passwordResetMaxAttempts = 5

	// Generous for a person who mistypes an address or waits for a slow
	// inbox, tight enough that scripted probing gets nothing useful.
	passwordResetRatePerMinute = 3.0
	passwordResetRateBurst     = 5.0
)

// lookupUserByIdentifier resolves a username-or-email login identifier. Login
// and password reset share it so a given string always means the same account
// in both places.
func lookupUserByIdentifier(db *gorm.DB, identifier string) (storage.User, bool) {
	identifier = strings.TrimSpace(identifier)
	if db == nil || identifier == "" {
		return storage.User{}, false
	}
	var user storage.User
	var err error
	if strings.Contains(identifier, "@") {
		err = db.Where("email = ?", normalizeEmail(identifier)).First(&user).Error
	} else {
		_, key := storage.NormalizeUsername(identifier)
		err = db.Where("username_key = ?", key).First(&user).Error
	}
	if err != nil {
		return storage.User{}, false
	}
	return user, true
}

// generatePasswordResetCode returns a uniformly random 6-digit code, zero
// padded so every code is the same length.
func generatePasswordResetCode() (string, error) {
	n, err := rand.Int(rand.Reader, big.NewInt(1000000))
	if err != nil {
		return "", err
	}
	return fmt.Sprintf("%06d", n.Int64()), nil
}

type passwordResetRequestBody struct {
	Identifier string `json:"identifier"`
}

// RequestPasswordReset issues a reset code to the address on file.
//
// It ALWAYS answers 204 with an empty body — for a malformed request, an
// unknown identifier, a known account with no address, a throttled caller, and
// a successful send alike. Any difference would turn this endpoint into an
// account-existence oracle. Response timing is not equalized (only a real
// account reaches the bcrypt hash); the per-IP limit bounds how fast that can
// be probed, and registration's 409 already discloses whether a username is
// taken.
func (h *AuthHandler) RequestPasswordReset(c *gin.Context) {
	var req passwordResetRequestBody
	// A malformed body simply yields an empty identifier, which resolves to
	// no account — the same silent 204 as every other miss.
	_ = c.ShouldBindJSON(&req)
	h.issuePasswordResetCode(c.Request.Context(), c.ClientIP(), req.Identifier)
	c.Header("Cache-Control", "no-store")
	c.Status(http.StatusNoContent)
}

// issuePasswordResetCode does the work behind RequestPasswordReset. Every
// failure path is logged and swallowed: the caller must not learn which one
// was taken.
func (h *AuthHandler) issuePasswordResetCode(ctx context.Context, clientIP, identifier string) {
	if h.DB == nil || h.Mail == nil || h.ResetLimiter == nil {
		return
	}
	// The per-IP bucket is what covers identifiers that resolve to nothing —
	// there is no user id to key on for those.
	if !h.ResetLimiter.Allow("ip:" + clientIP) {
		return
	}
	user, found := lookupUserByIdentifier(h.DB, identifier)
	if !found || user.Email == nil {
		return
	}
	if !h.ResetLimiter.Allow(fmt.Sprintf("user:%d", user.ID)) {
		return
	}

	code, err := generatePasswordResetCode()
	if err != nil {
		log.Printf("password reset: generating code: %v", err)
		return
	}
	hashed, err := bcrypt.GenerateFromPassword([]byte(code), bcrypt.DefaultCost)
	if err != nil {
		log.Printf("password reset: hashing code: %v", err)
		return
	}

	now := time.Now()
	if err := h.DB.Transaction(func(tx *gorm.DB) error {
		// Only the newest code may work, so retire any outstanding ones.
		if err := tx.Model(&storage.PasswordResetCode{}).
			Where("user_id = ? AND consumed_at IS NULL", user.ID).
			Update("consumed_at", now).Error; err != nil {
			return err
		}
		return tx.Create(&storage.PasswordResetCode{
			UserID:    user.ID,
			CodeHash:  string(hashed),
			ExpiresAt: now.Add(passwordResetCodeTTL),
		}).Error
	}); err != nil {
		log.Printf("password reset: storing code: %v", err)
		return
	}

	if err := h.Mail.SendPasswordResetCode(ctx, *user.Email, code); err != nil {
		log.Printf("password reset: sending code: %v", err)
	}
}

// ConfirmPasswordReset is implemented in the next task.
func (h *AuthHandler) ConfirmPasswordReset(c *gin.Context) {
	respondError(c, http.StatusNotImplemented, "Not implemented")
}
