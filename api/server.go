package api

import (
	"io/fs"
	"log"
	"mime"
	"net/http"
	"os"
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

func init() {
	// Ensure .js gets the right MIME type on all platforms
	mime.AddExtensionType(".js", "application/javascript")
	mime.AddExtensionType(".mjs", "application/javascript")
	mime.AddExtensionType(".css", "text/css")
	mime.AddExtensionType(".wasm", "application/wasm")
	mime.AddExtensionType(".svg", "image/svg+xml")
}

// setupFrontendRoutes serves the React SPA.
// Uses Gin's StaticFS for asset directories (correct MIME types via registered routes),
// and NoRoute only for the SPA HTML fallback.
func (s *Server) setupFrontendRoutes() {
	// Resolve the frontend filesystem: disk first (local dev), then embedded FS (deploy)
	var distFS fs.FS
	var indexHTML []byte
	source := "none"

	if diskDir, ok := locateFrontendDist(); ok {
		distFS = os.DirFS(diskDir)
		source = "disk: " + diskDir
	} else {
		sub, err := fs.Sub(web.DistFS, "dist")
		if err != nil {
			log.Printf("failed to open embedded dist: %v; serving API routes only", err)
			return
		}
		distFS = sub
		source = "embedded FS"
	}

	// Verify index.html exists
	var err error
	indexHTML, err = fs.ReadFile(distFS, "index.html")
	if err != nil {
		log.Printf("no index.html in %s; serving API routes only", source)
		return
	}
	log.Printf("serving frontend SPA from %s", source)

	// Register static asset directories as explicit Gin routes.
	// These get correct MIME types and never fall through to NoRoute.
	httpFS := http.FS(distFS)
	if assetsFS, err := fs.Sub(distFS, "assets"); err == nil {
		s.Router.StaticFS("/assets", http.FS(assetsFS))
	}
	if tileFacesFS, err := fs.Sub(distFS, "Regular_shortnames"); err == nil {
		s.Router.StaticFS("/Regular_shortnames", http.FS(tileFacesFS))
	}

	// Serve individual root-level static files
	rootFiles := []string{"vite.svg", "wasm_exec.js", "mahjong.wasm"}
	for _, name := range rootFiles {
		if _, err := fs.Stat(distFS, name); err == nil {
			name := name // capture
			s.Router.GET("/"+name, func(c *gin.Context) {
				c.FileFromFS(name, httpFS)
			})
		}
	}

	// NoRoute: serve index.html for all unmatched GET/HEAD requests (SPA routing)
	s.Router.NoRoute(func(c *gin.Context) {
		if strings.HasPrefix(c.Request.URL.Path, "/api/") {
			c.JSON(http.StatusNotFound, gin.H{"error": "Not found"})
			return
		}
		if c.Request.Method != http.MethodGet && c.Request.Method != http.MethodHead {
			c.Status(http.StatusNotFound)
			return
		}

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

// --- unexported helpers above, route handlers below ---

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
