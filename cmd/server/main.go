package main

import (
	"log"
	"os"
	"time"

	"github.com/plasma/fh-mahjong/api"
	"github.com/plasma/fh-mahjong/models"
	"github.com/redis/go-redis/v9"
	"gorm.io/driver/postgres"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"
)

func main() {
	log.Println("Booting Mahjong Server...")

	dsn := getEnv("DB_DSN", "host=localhost user=fh_admin password=fh_password dbname=fh_mahjong port=5432 sslmode=disable TimeZone=UTC")

	// Open DB connection with retry
	var db *gorm.DB
	var err error
	for i := 0; i < 5; i++ {
		db, err = gorm.Open(postgres.Open(dsn), &gorm.Config{
			Logger: logger.Default.LogMode(logger.Info),
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

	// Initialize WebSocket Hub
	hub := api.NewHub()
	go hub.Run()

	// Initialize Redis
	rdb := redis.NewClient(&redis.Options{
		Addr: getEnv("REDIS_ADDR", "localhost:6379"),
	})

	// 4. Start Matchmaking Service
	matchmaker := api.NewMatchmaker(rdb, db, hub)
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
