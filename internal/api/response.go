package api

import "github.com/gin-gonic/gin"

// respondError writes a JSON error body {"error": msg} with the given HTTP
// status. It is the single point for the API's error-response shape so the
// format stays consistent across handlers. Use abortError instead when the
// remaining handler chain must be stopped (e.g. from middleware).
func respondError(c *gin.Context, status int, msg string) {
	c.JSON(status, gin.H{"error": msg})
}

// abortError writes the same {"error": msg} body with the given status and
// aborts the request, so no later handlers in the chain run. Used by
// middleware (auth) where a failed check must short-circuit the request.
func abortError(c *gin.Context, status int, msg string) {
	c.AbortWithStatusJSON(status, gin.H{"error": msg})
}
