package api

import (
	"context"
	"crypto/rand"
	"errors"
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

// passwordResetGenericError is the single message every confirm failure gets:
// unknown identifier, no outstanding code, expired, already consumed, attempts
// spent, and simply wrong all read identically.
const passwordResetGenericError = "Invalid or expired reset code"

type passwordResetConfirmBody struct {
	Identifier  string `json:"identifier"`
	Code        string `json:"code"`
	NewPassword string `json:"newPassword" binding:"required,min=8"`
}

// ConfirmPasswordReset redeems a code and sets a new password.
//
// A rejected new password (too short) reports the binding error, since
// password-policy feedback says nothing about the account. Every other failure
// returns passwordResetGenericError. Success logs the account out everywhere:
// whoever triggered the reset may not be who was signed in.
func (h *AuthHandler) ConfirmPasswordReset(c *gin.Context) {
	var req passwordResetConfirmBody
	if err := c.ShouldBindJSON(&req); err != nil {
		respondError(c, http.StatusBadRequest, err.Error())
		return
	}
	if h.DB == nil {
		respondError(c, http.StatusServiceUnavailable, "Database is temporarily disabled.")
		return
	}

	user, found := lookupUserByIdentifier(h.DB, req.Identifier)
	if !found {
		respondError(c, http.StatusBadRequest, passwordResetGenericError)
		return
	}

	var record storage.PasswordResetCode
	if err := h.DB.Where("user_id = ? AND consumed_at IS NULL", user.ID).
		Order("id DESC").First(&record).Error; err != nil {
		if !errors.Is(err, gorm.ErrRecordNotFound) {
			log.Printf("password reset: loading code: %v", err)
		}
		respondError(c, http.StatusBadRequest, passwordResetGenericError)
		return
	}
	if time.Now().After(record.ExpiresAt) || record.Attempts >= passwordResetMaxAttempts {
		respondError(c, http.StatusBadRequest, passwordResetGenericError)
		return
	}

	// Spend the attempt BEFORE comparing, so the database — not a stale read —
	// is what enforces the cap. bcrypt sits inside the check-then-act window
	// for ~100ms; without this reservation, concurrent requests all pass a
	// check made against attempts=0 and turn a 5-guess budget into a
	// CPU-bound one against a 6-digit (~20-bit) code.
	reserved := h.DB.Model(&storage.PasswordResetCode{}).
		Where("id = ? AND attempts < ? AND consumed_at IS NULL AND expires_at > ?",
			record.ID, passwordResetMaxAttempts, time.Now()).
		Update("attempts", gorm.Expr("attempts + 1"))
	if reserved.Error != nil {
		log.Printf("password reset: reserving attempt: %v", reserved.Error)
		respondError(c, http.StatusBadRequest, passwordResetGenericError)
		return
	}
	if reserved.RowsAffected == 0 {
		respondError(c, http.StatusBadRequest, passwordResetGenericError)
		return
	}
	if bcrypt.CompareHashAndPassword([]byte(record.CodeHash), []byte(req.Code)) != nil {
		respondError(c, http.StatusBadRequest, passwordResetGenericError)
		return
	}

	hashed, err := bcrypt.GenerateFromPassword([]byte(req.NewPassword), bcrypt.DefaultCost)
	if err != nil {
		respondError(c, http.StatusInternalServerError, "Failed to hash password")
		return
	}
	now := time.Now()
	if err := h.DB.Transaction(func(tx *gorm.DB) error {
		if err := tx.Model(&storage.User{}).Where("id = ?", user.ID).
			Update("password_hash", string(hashed)).Error; err != nil {
			return err
		}
		if err := tx.Model(&storage.PasswordResetCode{}).
			Where("user_id = ? AND consumed_at IS NULL", user.ID).
			Update("consumed_at", now).Error; err != nil {
			return err
		}
		// Sign out every device: a reset is exactly the moment an existing
		// session may belong to whoever the owner is locking out.
		return tx.Where("user_id = ?", user.ID).Delete(&storage.UserSession{}).Error
	}); err != nil {
		respondError(c, http.StatusInternalServerError, "Failed to reset password")
		return
	}

	c.Header("Cache-Control", "no-store")
	c.Status(http.StatusNoContent)
}
