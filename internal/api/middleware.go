package api

import (
	"crypto/sha256"
	"crypto/subtle"
	"encoding/hex"
	"errors"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/plasma/fh-mahjong/internal/storage"
	"gorm.io/gorm"
)

var errInvalidSession = errors.New("invalid or expired session")

const csrfHeaderName = "X-CSRF-Token"

// AuthMiddleware authenticates an opaque database-backed session cookie.
// A missing database always fails closed.
func AuthMiddleware(db *gorm.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		if db == nil {
			abortError(c, http.StatusUnauthorized, "Authentication required")
			return
		}

		user, session, tokenHash, err := authenticateSessionRequest(db, c.Request)
		if err != nil {
			clearSessionCookies(c)
			abortError(c, http.StatusUnauthorized, "Invalid or expired session")
			return
		}

		if requiresCSRF(c.Request.Method) && subtle.ConstantTimeCompare([]byte(c.GetHeader(csrfHeaderName)), []byte(session.CSRFToken)) != 1 {
			abortError(c, http.StatusForbidden, "Invalid CSRF token")
			return
		}

		c.Set("userID", user.ID)
		c.Set("username", user.Username)
		c.Set("authUser", user)
		c.Set("sessionID", session.ID)
		c.Set("sessionTokenHash", tokenHash)
		c.Set("csrfToken", session.CSRFToken)
		c.Next()
	}
}

func authenticateSessionRequest(db *gorm.DB, r *http.Request) (storage.User, storage.UserSession, string, error) {
	if db == nil {
		return storage.User{}, storage.UserSession{}, "", errInvalidSession
	}
	rawToken, ok := readSessionCookie(r)
	if !ok {
		return storage.User{}, storage.UserSession{}, "", errInvalidSession
	}
	tokenHash := hashSessionToken(rawToken)
	var session storage.UserSession
	if err := db.Where("token_hash = ?", tokenHash).First(&session).Error; err != nil {
		return storage.User{}, storage.UserSession{}, "", errInvalidSession
	}
	if !session.ExpiresAt.After(time.Now()) {
		db.Delete(&session)
		return storage.User{}, storage.UserSession{}, "", errInvalidSession
	}
	var user storage.User
	if err := db.First(&user, session.UserID).Error; err != nil {
		db.Delete(&session)
		return storage.User{}, storage.UserSession{}, "", errInvalidSession
	}
	return user, session, tokenHash, nil
}

func readSessionCookie(r *http.Request) (string, bool) {
	name := devSessionCookieName
	if isProductionCookie() {
		name = prodSessionCookieName
	}
	if cookie, err := r.Cookie(name); err == nil && cookie.Value != "" {
		return cookie.Value, true
	}
	return "", false
}

func hashSessionToken(raw string) string {
	sum := sha256.Sum256([]byte(raw))
	return hex.EncodeToString(sum[:])
}

func requiresCSRF(method string) bool {
	switch method {
	case http.MethodGet, http.MethodHead, http.MethodOptions:
		return false
	default:
		return true
	}
}
