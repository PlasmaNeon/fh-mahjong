package api

import (
	"fmt"
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
)

// AuthMiddleware ensures the request has a valid JWT token
func AuthMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		authHeader := c.GetHeader("Authorization")
		if authHeader == "" {
			abortError(c, http.StatusUnauthorized, "Missing authorization header")
			return
		}

		parts := strings.Split(authHeader, " ")
		if len(parts) != 2 || parts[0] != "Bearer" {
			abortError(c, http.StatusUnauthorized, "Invalid authorization header format")
			return
		}

		tokenString := parts[1]

		token, err := jwt.Parse(tokenString, func(token *jwt.Token) (interface{}, error) {
			if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
				return nil, fmt.Errorf("unexpected signing method: %v", token.Header["alg"])
			}
			return jwtSecret, nil
		})

		if err != nil || !token.Valid {
			abortError(c, http.StatusUnauthorized, "Invalid or expired token")
			return
		}

		claims, ok := token.Claims.(jwt.MapClaims)
		if !ok {
			abortError(c, http.StatusUnauthorized, "Invalid token claims")
			return
		}

		userID := uint(claims["sub"].(float64))
		username := claims["username"].(string)

		// Attach to context for downstream handlers
		c.Set("userID", userID)
		c.Set("username", username)
		// Expose the original token expiry so handlers that re-issue a token (e.g.
		// profile update) can preserve it instead of extending the lifetime.
		if exp, ok := claims["exp"].(float64); ok {
			c.Set("tokenExp", int64(exp))
		}

		c.Next()
	}
}
