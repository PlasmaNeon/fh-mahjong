package api

import (
	"io/fs"
	"log"
	"mime"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/gin-contrib/gzip"
	"github.com/gin-gonic/gin"
	"github.com/plasma/fh-mahjong/internal/storage"
	"github.com/plasma/fh-mahjong/web"
	"golang.org/x/sync/singleflight"
	"gorm.io/gorm"
)

// Server encapsulates the Gin router and DB connection
type Server struct {
	Router     *gin.Engine
	DB         *gorm.DB
	Hub        *Hub
	Matchmaker *Matchmaker

	// In-memory paipu store for when DB is nil (local dev without Postgres)
	paipu   map[string]string // matchID -> paipu JSON
	paipuMu sync.RWMutex

	// reviewBuildGroup collapses concurrent review-build requests for the
	// SAME matchId into one in-flight build (round 21, Finding 1): without
	// this, a force-refresh storm (or plain unlucky concurrent load) against
	// one match id fires one authenticated /evaluate batch PER request
	// instead of sharing the single build actually in progress.
	reviewBuildGroup singleflight.Group
	// reviewBuildSem bounds how many review builds may run concurrently
	// SERVER-WIDE, independent of which match ids they're for (round 21,
	// Finding 1c): singleflight alone only dedupes identical match ids, so a
	// caller spamming ?force=1 across many distinct match ids could still
	// stack up unbounded concurrent authenticated /evaluate batches against
	// the policy server and starve live /act traffic. Acquired/released via
	// acquireReviewBuildSlot/releaseReviewBuildSlot — see review.go.
	reviewBuildSem chan struct{}
	// reviewBuildWaiters counts goroutines currently blocked trying to
	// acquire a review-build slot (round 22, Finding 1a): with
	// reviewBuildConcurrencyLimit slots already full, a request is queued
	// only while this stays at or below reviewBuildWaitQueueLimit; beyond
	// that it is rejected immediately (429) rather than queued unboundedly.
	// Accessed only via sync/atomic.
	reviewBuildWaiters int32
	// reviewRateLimiter enforces a small per-user token-bucket limit on
	// review-build POSTs (round 22, Finding 1d), independent of the
	// admission queue above: it caps how often ONE authenticated user can
	// even attempt to trigger a build, before that attempt ever touches the
	// shared semaphore/wait-queue.
	reviewRateLimiter *reviewRateLimiter
	// reviewShaCacheMu guards reviewShaCache below (round 23, Finding 1): the
	// public, unauthenticated GET /matches/:matchId/review route resolves
	// the policy server's live checkpoint sha via /healthz on every request
	// (see handleGetReview) — this short-TTL cache keeps that from hammering
	// /healthz once per casual page load.
	reviewShaCacheMu sync.Mutex
	reviewShaCache   reviewShaCacheEntry
	// reviewShaGroup coalesces concurrent /healthz refreshes into a single
	// in-flight call per policyURL (round 24, Finding 1): reviewShaCacheMu
	// above only protects the cache COPY itself — every one of N concurrent
	// GETs that observe an expired (or, pre-round-24, a failed-and-not-cached)
	// entry used to fire its OWN healthz round trip. With the resolution
	// itself keyed through this group, only the first caller to observe a
	// stale entry actually calls out; every concurrent caller for the same
	// policyURL waits on and shares that one result.
	reviewShaGroup singleflight.Group
}

// reviewShaCacheEntry is the short-TTL cache of the policy server's
// currently-served checkpoint identity, shared by every GET review request
// (round 23, Finding 1). Keyed on policyURL so a POLICY_SERVER_URL change
// (redeploy pointing at a different service) never serves a stale entry from
// the old one.
//
// Round 24, Finding 1: a failed resolution is now ALSO cached (err,
// non-nil) for reviewShaNegativeCacheTTL, so a healthz outage doesn't turn
// every single GET during the outage into its own healthz attempt — it is
// retried at most once per negative-TTL window, not once per request. A
// successful entry (err == nil) is still governed by the longer
// reviewShaCacheTTL as before.
type reviewShaCacheEntry struct {
	policyURL string
	sha       string
	legacy    bool
	err       error
	fetchedAt time.Time
}

// reviewShaCacheTTL bounds how long handleGetReview trusts a previously
// resolved live checkpoint sha before re-checking /healthz (round 23,
// Finding 1). Short enough that a promotion/rollback is picked up within one
// page-load's worth of staleness; long enough that a burst of replay-page
// opens (or a slow-clicking user) doesn't turn into a healthz call per
// request.
//
// A var, not a const, solely so tests can shrink it to 0 (see
// review_round23_test.go) and observe a promotion/rollback reflected on the
// very next GET rather than asserting against real wall-clock time.
var reviewShaCacheTTL = 10 * time.Second

// reviewShaNegativeCacheTTL bounds how long handleGetReview trusts a
// previously FAILED healthz resolution before retrying it (round 24,
// Finding 1). Deliberately much shorter than reviewShaCacheTTL — a real
// outage should still surface a fresh attempt reasonably promptly — but long
// enough that a burst of concurrent GETs arriving during an outage collapse
// onto one shared failed attempt (via reviewShaGroup) instead of each
// retrying the unreachable/erroring policy server on its own.
//
// A var, not a const, solely so tests can shrink or inspect it the same way
// reviewShaCacheTTL already is.
var reviewShaNegativeCacheTTL = 3 * time.Second

// reviewBuildConcurrencyLimit caps simultaneous in-flight review builds
// server-wide (round 21, Finding 1c). Kept small and fixed rather than
// configurable: review builds are a debugging/analysis path, not the hot
// gameplay path, and the whole point is to keep them from ever competing
// meaningfully with live /act traffic against the same policy server.
const reviewBuildConcurrencyLimit = 2

// reviewBuildWaitQueueLimit caps how many callers may wait for a review-build
// slot once reviewBuildConcurrencyLimit is exhausted (round 22, Finding 1a).
// Beyond capacity+queue (2+4 = 6 concurrently "admitted or waiting" builds),
// a new distinct-match build request is rejected immediately with 429 rather
// than queuing unboundedly — the original round-21 semaphore blocked forever
// with no bound and no way for a disconnected caller's goroutine to leave.
const reviewBuildWaitQueueLimit = 4

// NewServer initializes a new Server with all defined routes
func NewServer(db *gorm.DB, hub *Hub, matchmaker *Matchmaker) *Server {
	router := gin.Default()
	router.Use(credentialedCORSMiddleware())
	if err := router.SetTrustedProxies(loadTrustedProxies()); err != nil {
		log.Fatalf("invalid TRUSTED_PROXIES configuration: %v", err)
	}

	server := &Server{
		Router:            router,
		DB:                db,
		Hub:               hub,
		Matchmaker:        matchmaker,
		paipu:             make(map[string]string),
		reviewBuildSem:    make(chan struct{}, reviewBuildConcurrencyLimit),
		reviewRateLimiter: newReviewRateLimiter(),
	}

	if matchmaker != nil {
		matchmaker.PaipuStore = server.StorePaipu
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
		v1.GET("/auth/session", AuthMiddleware(s.DB), authHandler.Session)
		v1.DELETE("/auth/session", AuthMiddleware(s.DB), authHandler.Logout)
		v1.GET("/config", s.handleConfig)
		v1.POST("/tools/calc", s.handleCalc)
		v1.POST("/tools/shanten", s.handleShanten)
		v1.GET("/replays/:matchId", s.handleGetPaipu)
		v1.POST("/replays/:matchId", s.handleUploadPaipu)
		// GET is a pure cache lookup (never builds a report, never calls the
		// policy server) so it stays public. POST triggers an authenticated
		// batch of /evaluate calls against the policy server and is moved
		// into the protected group below (round 21, Finding 1): an
		// unauthenticated caller spamming ?force=1 against any known match
		// id could otherwise drive unlimited policy-server load and push
		// live RL agents into heuristic fallback.
		v1.GET("/matches/:matchId/review", s.handleGetReview)
		v1.GET("/ws", func(c *gin.Context) { ServeWs(s.Hub, s.DB, c) })

		// Protected routes
		protected := v1.Group("/")
		protected.Use(AuthMiddleware(s.DB))
		{
			protected.GET("/users/me", s.handleGetMe)
			protected.GET("/users/me/replays", s.handleReplayHistory)
			protected.PATCH("/users/me", authHandler.UpdateMe)
			protected.POST("/matchmaking/join", s.handleJoinQueue)
			protected.POST("/matchmaking/leave", s.handleLeaveQueue)

			protected.POST("/rooms", s.handlePrivateTableCreate)
			protected.GET("/rooms/:roomId", s.handlePrivateTableGet)
			protected.POST("/rooms/:roomId/join", s.handlePrivateTableJoin)
			protected.POST("/rooms/:roomId/seat", s.handlePrivateTableSeat)
			protected.POST("/rooms/:roomId/start", s.handlePrivateTableStart)
			protected.POST("/rooms/:roomId/mode", s.handlePrivateTableMode)

			protected.POST("/matches/:matchId/review", s.handlePostReview)
		}
	}

	s.setupFrontendRoutes()
}

// handleConfig exposes server-wide capability flags the frontend needs before
// rendering. rlAgentAvailable controls whether the private room offers the
// trained RL agent as a seat option.
func (s *Server) handleConfig(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{"rlAgentAvailable": s.Matchmaker.rlAgentAvailable()})
}

// StorePaipu saves paipu JSON to the in-memory store and DB (if available).
func (s *Server) StorePaipu(matchID, paipuJSON string) {
	s.paipuMu.Lock()
	s.paipu[matchID] = paipuJSON
	s.paipuMu.Unlock()

	if s.DB != nil {
		record := storage.PaipuRecord{ID: matchID, Data: paipuJSON}
		s.DB.Save(&record)
	}
}

// GetPaipu retrieves paipu JSON from the in-memory store.
func (s *Server) GetPaipu(matchID string) (string, bool) {
	s.paipuMu.RLock()
	data, ok := s.paipu[matchID]
	s.paipuMu.RUnlock()
	return data, ok
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

	// Compress text-based static assets (SVG tiles, JS/CSS bundles, wasm) on the
	// way out. Applied ONLY to these static routes — never globally — so it can
	// never interfere with the WebSocket upgrade (/api/v1/ws) or the binary
	// protobuf API responses. The tile SVGs are ~3x smaller gzipped.
	gz := gzip.Gzip(gzip.DefaultCompression)

	// Register static asset directories as explicit Gin routes.
	// These get correct MIME types and never fall through to NoRoute.
	httpFS := http.FS(distFS)
	if assetsFS, err := fs.Sub(distFS, "assets"); err == nil {
		// Vite emits content-hashed filenames here, so they can be cached
		// forever and treated as immutable.
		s.serveStaticSubdir("/assets", http.FS(assetsFS), "public, max-age=31536000, immutable", gz)
	}
	if tileFacesFS, err := fs.Sub(distFS, "Regular_shortnames"); err == nil {
		// Tile faces have stable (non-hashed) names, so cache for 30 days rather
		// than forever; bump the path or filenames if the artwork changes.
		s.serveStaticSubdir("/Regular_shortnames", http.FS(tileFacesFS), "public, max-age=2592000", gz)
	}

	// Serve individual root-level static files
	rootFiles := []string{"vite.svg", "wasm_exec.js", "mahjong.wasm"}
	for _, name := range rootFiles {
		if _, err := fs.Stat(distFS, name); err == nil {
			name := name // capture
			s.Router.GET("/"+name, gz, func(c *gin.Context) {
				c.FileFromFS(name, httpFS)
			})
		}
	}

	// NoRoute: serve index.html for all unmatched GET/HEAD requests (SPA routing)
	s.Router.NoRoute(func(c *gin.Context) {
		if strings.HasPrefix(c.Request.URL.Path, "/api/") {
			respondError(c, http.StatusNotFound, "Not found")
			return
		}
		if looksLikeStaticAssetRequest(c.Request.URL.Path) {
			c.Status(http.StatusNotFound)
			return
		}
		if c.Request.Method != http.MethodGet && c.Request.Method != http.MethodHead {
			c.Status(http.StatusNotFound)
			return
		}

		c.Data(http.StatusOK, "text/html; charset=utf-8", indexHTML)
	})
}

func (s *Server) serveStaticSubdir(routePrefix string, fileSystem http.FileSystem, cacheControl string, middleware ...gin.HandlerFunc) {
	serve := func(c *gin.Context) {
		relativePath := strings.TrimPrefix(c.Param("filepath"), "/")
		if relativePath == "" {
			c.Status(http.StatusNotFound)
			return
		}

		// Long-lived caching so static assets (hashed JS/CSS bundles, tile face
		// SVGs) are fetched once and then served from the browser cache instead
		// of being re-downloaded on every page load / SPA navigation. Without
		// this the ~48 tile SVGs (~1MB) are re-requested each time, which is
		// noticeably slow from a distant deploy region.
		if cacheControl != "" {
			c.Header("Cache-Control", cacheControl)
		}
		c.FileFromFS(relativePath, fileSystem)
	}

	handlers := append(append([]gin.HandlerFunc{}, middleware...), serve)
	s.Router.GET(routePrefix+"/*filepath", handlers...)
	s.Router.HEAD(routePrefix+"/*filepath", handlers...)
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

func looksLikeStaticAssetRequest(path string) bool {
	if strings.HasPrefix(path, "/assets/") || strings.HasPrefix(path, "/Regular_shortnames/") {
		return true
	}

	extension := strings.ToLower(filepath.Ext(path))
	switch extension {
	case ".js", ".mjs", ".css", ".wasm", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".map", ".json":
		return true
	default:
		return false
	}
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
		respondError(c, http.StatusBadRequest, err.Error())
		return
	}

	if err := s.Matchmaker.JoinQueue(userID.(uint), req.Ruleset); err != nil {
		respondError(c, http.StatusInternalServerError, "Failed to join queue")
		return
	}

	c.JSON(http.StatusOK, gin.H{"status": "queued", "ruleset": req.Ruleset})
}

// handleLeaveQueue safely releases an authenticated user from one ruleset
// queue. If the queue watcher already claimed them, the client must remain
// connected and wait for the match assignment instead of navigating away.
func (s *Server) handleLeaveQueue(c *gin.Context) {
	userID, _ := c.Get("userID")

	var req struct {
		Ruleset string `json:"ruleset" binding:"required"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if !s.Matchmaker.LeaveQueue(userID.(uint), req.Ruleset) {
		c.JSON(http.StatusConflict, gin.H{
			"status": "match_forming",
			"error":  "Your table is already forming. Stay connected to enter the match.",
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{"status": "left", "ruleset": canonicalRuleset(req.Ruleset)})
}

// handleGetMe returns the authenticated user's profile
func (s *Server) handleGetMe(c *gin.Context) {
	userID, _ := c.Get("userID")

	if s.DB == nil {
		respondError(c, http.StatusServiceUnavailable, "Database is temporarily disabled. Profile data is unavailable.")
		return
	}

	var user storage.User
	if err := s.DB.First(&user, userID).Error; err != nil {
		respondError(c, http.StatusNotFound, "User not found")
		return
	}

	user.PasswordHash = ""
	c.JSON(http.StatusOK, user)
}
