package main

import (
	"log"
	"os"

	"github.com/plasma/fh-mahjong/api"
	"gorm.io/gorm"
)

func main() {
	log.Println("Booting Mahjong Server...")

	// Open DB connection with retry
	var db *gorm.DB
	/*
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
	*/
	log.Println("Database connection is temporarily DISABLED. Running in guest-only mode.")

	// Initialize WebSocket Hub
	hub := api.NewHub()
	go hub.Run()

	// Initialize In-Memory Queue for Matchmaking
	inMemoryQueue := api.NewInMemoryQueue()

	// 4. Start Matchmaking Service
	matchmaker := api.NewMatchmaker(inMemoryQueue, db, hub)
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
