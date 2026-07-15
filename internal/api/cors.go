package api

import (
	"net/http"
	"net/url"
	"os"
	"strings"

	"github.com/gin-gonic/gin"
)

func configuredFrontendOrigins() map[string]struct{} {
	origins := make(map[string]struct{})
	for _, value := range strings.Split(os.Getenv("FRONTEND_ORIGINS"), ",") {
		if origin := strings.TrimSpace(value); origin != "" && origin != "*" {
			origins[strings.TrimSuffix(origin, "/")] = struct{}{}
		}
	}
	if !isProductionCookie() {
		origins["http://localhost:3000"] = struct{}{}
		origins["http://127.0.0.1:3000"] = struct{}{}
	}
	return origins
}

func originAllowed(r *http.Request) bool {
	origin := strings.TrimSuffix(strings.TrimSpace(r.Header.Get("Origin")), "/")
	if origin == "" {
		return true
	}
	parsed, err := url.Parse(origin)
	if err != nil || parsed.Scheme == "" || parsed.Host == "" || parsed.Path != "" {
		return false
	}
	if _, ok := configuredFrontendOrigins()[origin]; ok {
		return true
	}
	scheme := "http"
	if r.TLS != nil {
		scheme = "https"
	} else if forwarded := strings.TrimSpace(strings.Split(r.Header.Get("X-Forwarded-Proto"), ",")[0]); forwarded == "http" || forwarded == "https" {
		scheme = forwarded
	}
	return origin == scheme+"://"+r.Host
}

func credentialedCORSMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		origin := strings.TrimSuffix(strings.TrimSpace(c.GetHeader("Origin")), "/")
		if origin != "" {
			if !originAllowed(c.Request) {
				abortError(c, http.StatusForbidden, "Origin not allowed")
				return
			}
			c.Header("Access-Control-Allow-Origin", origin)
			c.Header("Access-Control-Allow-Credentials", "true")
			c.Header("Access-Control-Allow-Headers", "Content-Type, X-CSRF-Token")
			c.Header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
			c.Header("Vary", "Origin")
		}
		if c.Request.Method == http.MethodOptions {
			c.AbortWithStatus(http.StatusNoContent)
			return
		}
		c.Next()
	}
}
