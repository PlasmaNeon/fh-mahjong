package main

import (
	"log"
	"os"
	"strings"
	"time"

	"github.com/plasma/fh-mahjong/api"
	"github.com/plasma/fh-mahjong/bot"
	"github.com/plasma/fh-mahjong/bot/remote"
	"github.com/plasma/fh-mahjong/models"
	"gorm.io/driver/postgres"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"
)

func main() {
	log.Println("Booting Mahjong Server...")

	// Open DB connection: use DATABASE_URL if set, otherwise try local docker-compose defaults
	var db *gorm.DB
	dsn, hasExplicitDSN := os.LookupEnv("DATABASE_URL")
	if !hasExplicitDSN {
		dsn = "host=localhost user=fh_admin password=fh_password dbname=fh_mahjong port=5433 sslmode=disable TimeZone=UTC"
	}
	if hasExplicitDSN {
		var err error
		for i := 0; i < 5; i++ {
			db, err = gorm.Open(postgres.Open(dsn), &gorm.Config{
				Logger: logger.Default.LogMode(logger.Warn),
			})
			if err == nil {
				break
			}
			log.Printf("Failed to connect to database. Retrying in 2 seconds... (%v)", err)
			time.Sleep(2 * time.Second)
		}
		if err != nil {
			log.Fatalf("Could not connect to database after 5 attempts: %v", err)
		}
		log.Println("Successfully connected to Database. Running migrations...")
		if err := models.AutoMigrate(db); err != nil {
			log.Fatalf("Failed to run schema migrations: %v", err)
		}
	} else {
		// Local dev: try docker-compose defaults, but don't crash if unavailable
		var err error
		db, err = gorm.Open(postgres.Open(dsn), &gorm.Config{
			Logger: logger.Default.LogMode(logger.Warn),
		})
		if err != nil {
			log.Printf("Local database not available, running without DB: %v", err)
			db = nil
		} else {
			log.Println("Connected to local database. Running migrations...")
			if err := models.AutoMigrate(db); err != nil {
				log.Fatalf("Failed to run schema migrations: %v", err)
			}
		}
	}

	// Initialize WebSocket Hub
	hub := api.NewHub()
	go hub.Run()

	// Initialize In-Memory Queue for Matchmaking
	inMemoryQueue := api.NewInMemoryQueue()

	// 4. Start Matchmaking Service
	matchmaker := api.NewMatchmaker(inMemoryQueue, db, hub)
	if remotePolicyURL := strings.TrimSpace(os.Getenv("AI_BOT_POLICY_URL")); remotePolicyURL != "" {
		log.Printf("Using remote AI bot policy endpoint for automated seats: %s", remotePolicyURL)
		matchmaker.BotPolicyFactory = func() bot.Policy {
			return remote.NewHTTPPolicy(remotePolicyURL)
		}
	}
	go matchmaker.StartQueueWatcher("hometown")
	go matchmaker.StartPrivateTableWatcher()

	// Initialize Server
	server := api.NewServer(db, hub, matchmaker)

	port := getEnv("PORT", "8080")
	log.Printf("Starting HTTP server on port %s", port)

	if err := server.Router.Run(":" + port); err != nil {
		log.Fatalf("Server exited with error: %v", err)
	}
}

func getEnv(key, fallback string) string {
	if value, ok := os.LookupEnv(key); ok {
		return value
	}
	return fallback
}
