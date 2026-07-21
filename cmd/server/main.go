package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/plasma/fh-mahjong/internal/api"
	"github.com/plasma/fh-mahjong/internal/bot"
	"github.com/plasma/fh-mahjong/internal/bot/remote"
	"github.com/plasma/fh-mahjong/internal/rl"
	"github.com/plasma/fh-mahjong/internal/rules/shanten"
	"github.com/plasma/fh-mahjong/internal/storage"
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

// defaultShadowEventWindow is used for RL_AGENT_SHADOW_EVENT_WINDOW when the
// env var is unset.
const defaultShadowEventWindow = 128

func main() {
	log.Println("Booting Mahjong Server...")

	// Build the shanten lookup tables off the critical path. The first call is
	// slow (it enumerates every hand shape); doing it here at boot means the
	// first game's initial BroadcastState doesn't block for ~15s, which would
	// otherwise leave the client stuck on "Waiting for server to deal".
	go func() {
		start := time.Now()
		shanten.Prewarm()
		log.Printf("Shanten lookup tables ready in %v", time.Since(start))
	}()

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
		if err := storage.AutoMigrate(db); err != nil {
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
			if err := storage.AutoMigrate(db); err != nil {
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

	// RL_AGENT_EVENT_WINDOW declares the event-history wire contract every
	// PRIMARY remote policy speaks (matchmaking-queue bots AND the
	// private-room RL agent) — same env family as RL_AGENT_POLICY_URL /
	// RL_AGENT_CHECKPOINT_ID / RL_AGENT_SHADOW_EVENT_WINDOW, and the same
	// parsing semantics internal/api's reviewEventWindow uses for the review
	// path. Unset/invalid/out-of-bound values fail closed to 0 (event-free,
	// byte-identical to pre-event-contract behavior) rather than serving a
	// mismatched wire form.
	rlEventWindow := parseEventWindowEnv("RL_AGENT_EVENT_WINDOW", 0)
	log.Printf("Primary remote policy event window: %d (RL_AGENT_EVENT_WINDOW)", rlEventWindow)

	// An explicit AI_BOT_POLICY_URL routes ALL matchmaking-queue bots through
	// the remote policy (unchanged behavior). For the private-room RL agent we
	// fall back to a local default endpoint, so the option works out of the box
	// in local dev without any env var.
	explicitPolicyURL := strings.TrimSpace(os.Getenv("AI_BOT_POLICY_URL"))
	if explicitPolicyURL != "" {
		log.Printf("Using remote AI bot policy endpoint for matchmaking seats: %s", explicitPolicyURL)
		// Shared instance (HTTPPolicy is safe for concurrent use — atomic
		// stats counters, no other mutable state) rather than a fresh policy
		// per bot: lets one startup healthz validation cover every
		// matchmaking-queue bot this factory ever hands out.
		botPolicy := remote.NewHTTPPolicy(explicitPolicyURL, remote.WithEventWindow(rlEventWindow))
		matchmaker.BotPolicyFactory = func() bot.Policy {
			return botPolicy
		}
		validatePolicyContractAsync("matchmaking bot policy (AI_BOT_POLICY_URL)", botPolicy)
	}

	// RL endpoint for the private-room agent. RL_AGENT_POLICY_URL points it at a
	// dedicated policy server (e.g. the docker-compose `policy` service) without
	// routing matchmaking bots through it; otherwise it follows AI_BOT_POLICY_URL,
	// and finally the local default that the Go server can autostart.
	rlOverride := strings.TrimSpace(os.Getenv("RL_AGENT_POLICY_URL"))
	rlPolicyURL, rlIsLocalDefault := rlEndpointURL(rlOverride, explicitPolicyURL)
	// Share one HTTP client (and its connection pool) across every RL seat the
	// resolver creates, rather than letting each NewHTTPPolicy spin up its own.
	// Reusing connections avoids socket churn/exhaustion when many RL seats or
	// rooms start. 750ms matches the remote package's default per-call timeout.
	rlHTTPClient := &http.Client{Timeout: 750 * time.Millisecond}
	// RL_AGENT_SHADOW_POLICY_URL, if set, wraps the RESOLVED RL primary policy
	// (the currently-deployed champion serving real seats) with a
	// bot.ShadowPolicy that silently mirrors each decision to a second,
	// candidate event-aware HTTPPolicy for comparison. Shadow mode never
	// affects what actually gets played — the primary always answers, the
	// shadow's evaluation runs on a background worker — so a candidate policy
	// can be evaluated against live traffic before it is ever promoted to
	// serve directly.
	shadowPolicyURL := strings.TrimSpace(os.Getenv("RL_AGENT_SHADOW_POLICY_URL"))
	var shadowPolicy bot.ContextPolicy
	if shadowPolicyURL != "" {
		window := shadowEventWindow(defaultShadowEventWindow)
		shadowHTTPPolicy := remote.NewHTTPPolicy(
			shadowPolicyURL,
			remote.WithHTTPClient(rlHTTPClient),
			remote.WithEventWindow(window),
		)
		shadowPolicy = shadowHTTPPolicy
		log.Printf(
			"RL agent shadow policy enabled: endpoint=%s event_window=%d (mirrors private-room RL decisions only; never serves them)",
			shadowPolicyURL, window,
		)
		validatePolicyContractAsync("RL shadow policy", shadowHTTPPolicy)
	}

	// The RL primary is shared (like the matchmaking bot policy above) rather
	// than rebuilt per seat, so one startup healthz validation covers every
	// private-room RL seat the resolver ever hands out.
	rlPrimaryPolicy := remote.NewHTTPPolicy(rlPolicyURL, remote.WithHTTPClient(rlHTTPClient), remote.WithEventWindow(rlEventWindow))
	validatePolicyContractAsync("RL primary policy", rlPrimaryPolicy)

	// Let private-room hosts assign a trained RL agent per seat. The remote
	// HTTP policy already falls back to heuristic per-decision, so a transient
	// outage mid-match degrades gracefully rather than stalling.
	matchmaker.SeatPolicyResolver = func(d pb.Difficulty) (bot.Policy, error) {
		if d == pb.Difficulty_DIFFICULTY_RL {
			if shadowPolicy != nil {
				return bot.NewShadowPolicy(rlPrimaryPolicy, shadowPolicy, 64), nil
			}
			return rlPrimaryPolicy, nil
		}
		return bot.NewPolicy(d)
	}
	// Surface the RL option only while the model server is actually reachable.
	rlHealth := remote.NewHealthChecker(rlPolicyURL)
	matchmaker.RLAgentAvailable = rlHealth.Healthy
	// Label RL seats in the paipu with the served checkpoint identity
	// (basename@step from /healthz — paipu are public, so never a URL or
	// filesystem path). When the policy server reports nothing, fall back to
	// the operator-configured RL_AGENT_CHECKPOINT_ID; empty means unknown.
	rlCheckpointLabel := strings.TrimSpace(os.Getenv("RL_AGENT_CHECKPOINT_ID"))
	matchmaker.RLPolicyIdentity = func() string {
		if id := rlHealth.Identity(); id != "" {
			return id
		}
		return rlCheckpointLabel
	}
	log.Printf("Private-room RL agent endpoint: %s (offered when reachable)", rlPolicyURL)

	// When using the local default endpoint, bring the policy server up as a
	// managed child process so the RL agent connects automatically on boot.
	// Skipped when an external endpoint is configured (AI_BOT_POLICY_URL or
	// RL_AGENT_POLICY_URL) — e.g. the docker-compose `policy` service.
	var policyCleanup func()
	if rlIsLocalDefault {
		policyCleanup = maybeStartPolicyServer(rlPolicyURL)
	}
	// On SIGINT/SIGTERM (Ctrl-C, redeploy), persist every in-flight match as
	// "aborted" with its partial paipu before exiting, then stop the managed
	// policy child (if any).
	installSignalCleanup(func() {
		matchmaker.DrainActiveRooms(10 * time.Second)
		if policyCleanup != nil {
			policyCleanup()
		}
	})

	go matchmaker.StartQueueWatcher("fenghua")
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

// shadowEventWindow reads RL_AGENT_SHADOW_EVENT_WINDOW, falling back to
// defaultWindow per parseEventWindowEnv's semantics.
func shadowEventWindow(defaultWindow uint32) uint32 {
	return parseEventWindowEnv("RL_AGENT_SHADOW_EVENT_WINDOW", defaultWindow)
}

// parseEventWindowEnv reads envVar as an event-history window: unset/empty
// falls back to defaultWindow; unparseable or exceeding
// rl.MaxEventHistoryWindow (512 — same bound internal/api's
// reviewEventWindow enforces) is rejected outright (logged, not clamped)
// rather than silently truncated, matching internal/rl's refusal semantics
// elsewhere (env.go, searchpool.go). Shared by every event-window env var in
// this package (RL_AGENT_EVENT_WINDOW, RL_AGENT_SHADOW_EVENT_WINDOW) so their
// parsing/rejection rules can never drift apart.
func parseEventWindowEnv(envVar string, defaultWindow uint32) uint32 {
	raw := strings.TrimSpace(os.Getenv(envVar))
	if raw == "" {
		return defaultWindow
	}
	n, err := strconv.ParseUint(raw, 10, 32)
	if err != nil {
		log.Printf("ignoring invalid %s %q: %v (using default %d)", envVar, raw, err, defaultWindow)
		return defaultWindow
	}
	if n > rl.MaxEventHistoryWindow {
		log.Printf("ignoring %s %q: exceeds maximum %d (using default %d)", envVar, raw, rl.MaxEventHistoryWindow, defaultWindow)
		return defaultWindow
	}
	return uint32(n)
}

// validatePolicyContractAsync probes policy's /healthz in the background at
// startup (HTTPPolicy.ValidateServer — previously constructed but never
// invoked), confirming the served checkpoint's event-window/contract-version
// match what this Go server was configured to speak. Failures are logged
// LOUDLY but never fatal and never block boot: the policy server commonly
// isn't up yet when the backend starts (autostart launches it as a child
// process, and the RL option only surfaces once its own health check
// passes), and a genuine mismatch is still caught fail-closed at decision
// time by the heuristic fallback and serve_policy's own 400s. label
// identifies which policy in the logs (matchmaking bot / RL primary / RL
// shadow).
func validatePolicyContractAsync(label string, policy *remote.HTTPPolicy) {
	if policy == nil {
		return
	}
	go func() {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if err := policy.ValidateServer(ctx); err != nil {
			log.Printf("POLICY CONTRACT MISMATCH / server unreachable (%s): %v — serving falls back to heuristic per-decision until this is resolved", label, err)
			return
		}
		log.Printf("policy contract validated (%s)", label)
	}()
}
