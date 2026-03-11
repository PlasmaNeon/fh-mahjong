package api

import (
	"io/fs"
	"log"
	"net/http"
	"os"
	"path"
	"path/filepath"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/plasma/fh-mahjong/models"
	"github.com/plasma/fh-mahjong/web"
	"gorm.io/gorm"
)

// Server encapsulates the Gin router and DB connection
type Server struct {
	Router     *gin.Engine
	DB         *gorm.DB
	Hub        *Hub
	Matchmaker *Matchmaker
}

// NewServer initializes a new Server with all defined routes
func NewServer(db *gorm.DB, hub *Hub, matchmaker *Matchmaker) *Server {
	router := gin.Default()
	if err := router.SetTrustedProxies(loadTrustedProxies()); err != nil {
		log.Fatalf("invalid TRUSTED_PROXIES configuration: %v", err)
	}

	server := &Server{
		Router:     router,
		DB:         db,
		Hub:        hub,
		Matchmaker: matchmaker,
	}

	server.setupRoutes()
	return server
}

func (s *Server) setupRoutes() {
	authHandler := &AuthHandler{DB: s.DB}

	v1 := s.Router.Group("/api/v1")
	{
		// Public routes
		v1.POST("/auth/register", authHandler.Register)
		v1.POST("/auth/login", authHandler.Login)
		v1.POST("/auth/guest", authHandler.GuestLogin)
		v1.POST("/calc", s.handleCalc)
		v1.GET("/ws", func(c *gin.Context) { ServeWs(s.Hub, c) })

		// Protected routes
		protected := v1.Group("/")
		protected.Use(AuthMiddleware())
		{
			protected.GET("/users/me", s.handleGetMe)
			protected.POST("/matchmaking/join", s.handleJoinQueue)
			protected.POST("/matchmaking/private", s.handleJoinPrivate)
		}
	}

	s.setupFrontendRoutes()
}

// setupFrontendRoutes serves the React SPA.
// Priority: disk (for local dev with Vite hot-reload) → embedded FS (for deploy).
func (s *Server) setupFrontendRoutes() {
	// 1. Try disk first (local development)
	if diskDir, ok := locateFrontendDist(); ok {
		log.Printf("serving frontend SPA from disk: %s", diskDir)
		s.mountSPAFromDisk(diskDir)
		return
	}

	// 2. Fall back to embedded FS (production deploy)
	distFS, err := fs.Sub(web.DistFS, "dist")
	if err != nil {
		log.Printf("failed to open embedded dist: %v; serving API routes only", err)
		return
	}

	// Verify the embedded FS actually has index.html
	if _, err := fs.Stat(distFS, "index.html"); err != nil {
		log.Printf("embedded dist has no index.html; serving API routes only")
		return
	}

	log.Printf("serving frontend SPA from embedded FS")
	s.mountSPAFromFS(distFS)
}

// mountSPAFromDisk serves the SPA from a directory on the local filesystem.
func (s *Server) mountSPAFromDisk(distDir string) {
	indexPath := filepath.Join(distDir, "index.html")

	s.Router.NoRoute(func(c *gin.Context) {
		if strings.HasPrefix(c.Request.URL.Path, "/api/") {
			c.JSON(http.StatusNotFound, gin.H{"error": "Not found"})
			return
		}
		if c.Request.Method != http.MethodGet && c.Request.Method != http.MethodHead {
			c.Status(http.StatusNotFound)
			return
		}

		requestPath := strings.TrimPrefix(path.Clean("/"+c.Request.URL.Path), "/")
		if requestPath == "" {
			c.File(indexPath)
			return
		}

		candidate := filepath.Join(distDir, filepath.FromSlash(requestPath))
		if isPathWithinBase(distDir, candidate) {
			if info, err := os.Stat(candidate); err == nil && !info.IsDir() {
				c.File(candidate)
				return
			}
		}

		c.File(indexPath)
	})
}

// mountSPAFromFS serves the SPA from an embedded (or any) fs.FS.
func (s *Server) mountSPAFromFS(distFS fs.FS) {
	indexHTML, err := fs.ReadFile(distFS, "index.html")
	if err != nil {
		log.Printf("failed to read embedded index.html: %v", err)
		return
	}

	fileServer := http.FileServer(http.FS(distFS))

	s.Router.NoRoute(func(c *gin.Context) {
		if strings.HasPrefix(c.Request.URL.Path, "/api/") {
			c.JSON(http.StatusNotFound, gin.H{"error": "Not found"})
			return
		}
		if c.Request.Method != http.MethodGet && c.Request.Method != http.MethodHead {
			c.Status(http.StatusNotFound)
			return
		}

		requestPath := strings.TrimPrefix(path.Clean("/"+c.Request.URL.Path), "/")

		// Try serving the exact file (JS, CSS, images, etc.)
		if requestPath != "" {
			if _, err := fs.Stat(distFS, requestPath); err == nil {
				fileServer.ServeHTTP(c.Writer, c.Request)
				return
			}
		}

		// Fall back to index.html for SPA client-side routing
		c.Data(http.StatusOK, "text/html; charset=utf-8", indexHTML)
	})
}

func loadTrustedProxies() []string {
	raw := strings.TrimSpace(os.Getenv("TRUSTED_PROXIES"))
	if raw == "" {
		return nil
	}

	parts := strings.Split(raw, ",")
	proxies := make([]string, 0, len(parts))
	for _, part := range parts {
		proxy := strings.TrimSpace(part)
		if proxy != "" {
			proxies = append(proxies, proxy)
		}
	}

	if len(proxies) == 0 {
		return nil
	}

	return proxies
}

func locateFrontendDist() (string, bool) {
	if configured := strings.TrimSpace(os.Getenv("WEB_DIST_DIR")); configured != "" {
		if hasIndexHTML(configured) {
			return configured, true
		}
		return "", false
	}

	candidates := []string{
		filepath.Join("web", "dist"),
	}

	if exePath, err := os.Executable(); err == nil {
		exeDir := filepath.Dir(exePath)
		candidates = append(candidates,
			filepath.Join(exeDir, "web", "dist"),
			filepath.Join(exeDir, "..", "web", "dist"),
		)
	}

	for _, candidate := range candidates {
		if hasIndexHTML(candidate) {
			return candidate, true
		}
	}

	return "", false
}

func hasIndexHTML(dir string) bool {
	info, err := os.Stat(filepath.Join(dir, "index.html"))
	return err == nil && !info.IsDir()
}

func isPathWithinBase(base, target string) bool {
	relative, err := filepath.Rel(base, target)
	if err != nil {
		return false
	}

	return relative != ".." && !strings.HasPrefix(relative, ".."+string(filepath.Separator))
}

// handleJoinQueue lets an authenticated user queue up for a game
func (s *Server) handleJoinQueue(c *gin.Context) {
	userID, _ := c.Get("userID")

	var req struct {
		Ruleset string `json:"ruleset" binding:"required"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := s.Matchmaker.JoinQueue(userID.(uint), req.Ruleset); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to join queue"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"status": "queued", "ruleset": req.Ruleset})
}

// handleJoinPrivate lets a user manually connect to a private link/table identifier
func (s *Server) handleJoinPrivate(c *gin.Context) {
	userID, _ := c.Get("userID")
	username, _ := c.Get("username")

	var req struct {
		TableID string `json:"tableId" binding:"required"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := s.Matchmaker.JoinPrivateTable(userID.(uint), username.(string), req.TableID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to join private table"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"status": "queued", "table": req.TableID})
}

// handleGetMe returns the authenticated user's profile
func (s *Server) handleGetMe(c *gin.Context) {
	userID, _ := c.Get("userID")

	if s.DB == nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{"error": "Database is temporarily disabled. Profile data is unavailable."})
		return
	}

	var user models.User
	if err := s.DB.First(&user, userID).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "User not found"})
		return
	}

	user.PasswordHash = ""
	c.JSON(http.StatusOK, user)
}
