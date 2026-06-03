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
	pb "github.com/plasma/fh-mahjong/proto"
	"gorm.io/driver/postgres"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"
)

// defaultRLPolicyURL is the local serve_policy.py endpoint used for the
// private-room RL agent when AI_BOT_POLICY_URL is not set. The option is only
// offered when this endpoint passes its /healthz probe, so defaulting it is
// safe even when no model server is running.
const defaultRLPolicyURL = "http://127.0.0.1:8765/act"

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
	// An explicit AI_BOT_POLICY_URL routes ALL matchmaking-queue bots through
	// the remote policy (unchanged behavior). For the private-room RL agent we
	// fall back to a local default endpoint, so the option works out of the box
	// in local dev without any env var.
	explicitPolicyURL := strings.TrimSpace(os.Getenv("AI_BOT_POLICY_URL"))
	if explicitPolicyURL != "" {
		log.Printf("Using remote AI bot policy endpoint for matchmaking seats: %s", explicitPolicyURL)
		matchmaker.BotPolicyFactory = func() bot.Policy {
			return remote.NewHTTPPolicy(explicitPolicyURL)
		}
	}

	// RL endpoint for the private-room agent. RL_AGENT_POLICY_URL points it at a
	// dedicated policy server (e.g. the docker-compose `policy` service) without
	// routing matchmaking bots through it; otherwise it follows AI_BOT_POLICY_URL,
	// and finally the local default that the Go server can autostart.
	rlOverride := strings.TrimSpace(os.Getenv("RL_AGENT_POLICY_URL"))
	rlPolicyURL, rlIsLocalDefault := rlEndpointURL(rlOverride, explicitPolicyURL)
	// Let private-room hosts assign a trained RL agent per seat. The remote
	// HTTP policy already falls back to heuristic per-decision, so a transient
	// outage mid-match degrades gracefully rather than stalling.
	matchmaker.SeatPolicyResolver = func(d pb.Difficulty) (bot.Policy, error) {
		if d == pb.Difficulty_DIFFICULTY_RL {
			return remote.NewHTTPPolicy(rlPolicyURL), nil
		}
		return bot.NewPolicy(d)
	}
	// Surface the RL option only while the model server is actually reachable.
	rlHealth := remote.NewHealthChecker(rlPolicyURL)
	matchmaker.RLAgentAvailable = rlHealth.Healthy
	log.Printf("Private-room RL agent endpoint: %s (offered when reachable)", rlPolicyURL)

	// When using the local default endpoint, bring the policy server up as a
	// managed child process so the RL agent connects automatically on boot.
	// Skipped when an external endpoint is configured (AI_BOT_POLICY_URL or
	// RL_AGENT_POLICY_URL) — e.g. the docker-compose `policy` service.
	if rlIsLocalDefault {
		installSignalCleanup(maybeStartPolicyServer(rlPolicyURL))
	}

	go matchmaker.StartQueueWatcher("hometown")
	go matchmaker.StartQueueWatcher("chongci-fh")

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
