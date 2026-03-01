package api

import (
	"net/http"

	"github.com/gin-gonic/gin"
	"github.com/plasma/fh-mahjong/models"
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

	// CORS middleware could be added here

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

	var user models.User
	if err := s.DB.First(&user, userID).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "User not found"})
		return
	}

	user.PasswordHash = ""
	c.JSON(http.StatusOK, user)
}
