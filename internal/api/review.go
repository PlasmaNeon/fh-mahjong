package api

import (
	"encoding/json"
	"errors"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/plasma/fh-mahjong/internal/bot/remote"
	"github.com/plasma/fh-mahjong/internal/engine"
	"github.com/plasma/fh-mahjong/internal/review"
	"github.com/plasma/fh-mahjong/internal/rl"
	"github.com/plasma/fh-mahjong/internal/storage"
	"gorm.io/gorm"
)

// parseReviewEventWindowEnv reads envVar as an event-history window using the
// same semantics as cmd/server's parseEventWindowEnv (which this package
// cannot import — it lives in package main): unset/empty falls back to
// defaultWindow; unparseable or exceeding rl.MaxEventHistoryWindow is
// rejected outright (logged, not clamped) rather than silently truncated,
// matching internal/rl's refusal semantics elsewhere (env.go, searchpool.go).
// Shared by every event-window env var this package reads (REVIEW_EVENT_WINDOW,
// RL_AGENT_EVENT_WINDOW) so their parsing/rejection rules can never drift
// apart.
func parseReviewEventWindowEnv(envVar string, defaultWindow uint32) uint32 {
	raw := strings.TrimSpace(os.Getenv(envVar))
	if raw == "" {
		return defaultWindow
	}
	n, err := strconv.ParseUint(raw, 10, 32)
	if err != nil {
		log.Printf("review: ignoring invalid %s %q: %v", envVar, raw, err)
		return defaultWindow
	}
	if n > rl.MaxEventHistoryWindow {
		log.Printf("review: ignoring %s %q: exceeds maximum %d", envVar, raw, rl.MaxEventHistoryWindow)
		return defaultWindow
	}
	return uint32(n)
}

// reviewEventWindow resolves the event-history window for the review
// client, which talks to POLICY_SERVER_URL (policyURL) — a server that may
// serve a DIFFERENT checkpoint than the one RL_AGENT_POLICY_URL/
// AI_BOT_POLICY_URL and RL_AGENT_EVENT_WINDOW describe in cmd/server/main.go
// (adversarial round 7, Finding 2).
//
// REVIEW_EVENT_WINDOW, when set (same parse/bound semantics as every other
// event-window env var, via parseReviewEventWindowEnv), always wins — it
// describes POLICY_SERVER_URL's own contract directly and is never
// overridden by RL_AGENT_EVENT_WINDOW.
//
// When REVIEW_EVENT_WINDOW is unset, falling back to RL_AGENT_EVENT_WINDOW is
// only safe when review traffic and RL traffic actually hit the same
// service: policyURL is empty (no reviewer configured — moot), or policyURL
// equals the resolved RL agent endpoint (RL_AGENT_POLICY_URL, else
// AI_BOT_POLICY_URL — mirroring cmd/server's rlEndpointURL fallback chain,
// minus the local-default case, which review — a POLICY_SERVER_URL-only
// path — never hits). Otherwise this fails closed to 0 (event-free) rather
// than guessing a wire contract POLICY_SERVER_URL might not actually speak,
// the same fail-closed contract resolveAIBotEventWindow established in
// cmd/server for the AI_BOT_POLICY_URL/RL_AGENT_POLICY_URL split.
func reviewEventWindow(policyURL string) uint32 {
	if raw := strings.TrimSpace(os.Getenv("REVIEW_EVENT_WINDOW")); raw != "" {
		return parseReviewEventWindowEnv("REVIEW_EVENT_WINDOW", 0)
	}

	rlOverride := strings.TrimSpace(os.Getenv("RL_AGENT_POLICY_URL"))
	effectiveRLURL := rlOverride
	if effectiveRLURL == "" {
		effectiveRLURL = strings.TrimSpace(os.Getenv("AI_BOT_POLICY_URL"))
	}

	if policyURL != "" && effectiveRLURL != "" && !sameReviewService(policyURL, effectiveRLURL) {
		log.Printf("review: POLICY_SERVER_URL (%s) differs from the resolved RL agent endpoint (%s); REVIEW_EVENT_WINDOW is unset — defaulting review event window to 0 rather than inheriting RL_AGENT_EVENT_WINDOW for a possibly different service", policyURL, effectiveRLURL)
		return 0
	}

	return parseReviewEventWindowEnv("RL_AGENT_EVENT_WINDOW", 0)
}

// sameReviewService reports whether baseURL (POLICY_SERVER_URL, a BASE URL —
// HTTPPolicyClient appends "/evaluate" to it) and rlURL (the resolved RL
// agent endpoint, RL_AGENT_POLICY_URL/AI_BOT_POLICY_URL, which ends in
// "/act") name the same backing service (adversarial round 8).
//
// A literal string comparison undercounts same-service configs: in the
// production-shaped setup POLICY_SERVER_URL=http://policy:8765 and
// RL_AGENT_POLICY_URL=http://policy:8765/act describe the same server, but
// compare unequal, which forced the review window to 0 and made every
// uncached review 502 once RL_AGENT_EVENT_WINDOW mattered. Delegates to
// remote.SameServiceEndpoint — the single shared endpoint-identity
// normalization also used by cmd/server's resolveAIBotEventWindow
// (adversarial round 9: two separate ad hoc normalizations here and there
// drifted in what they tolerated, e.g. host case and default ports).
func sameReviewService(baseURL, rlURL string) bool {
	return remote.SameServiceEndpoint(baseURL, rlURL)
}

// handleGetReview serves the newest cached MatchReview for a match. It is a
// pure cache lookup — it never builds a report. DB nil or no cached row →
// 404.
func (s *Server) handleGetReview(c *gin.Context) {
	matchID := c.Param("matchId")
	if matchID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "matchId is required"})
		return
	}

	if s.DB == nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "no cached review for this match"})
		return
	}

	var row storage.MatchReview
	err := s.DB.Where("match_id = ?", matchID).Order("created_at DESC").First(&row).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		c.JSON(http.StatusNotFound, gin.H{"error": "no cached review for this match"})
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to load cached review"})
		return
	}

	c.Data(http.StatusOK, "application/json", []byte(row.ReportJSON))
}

// handlePostReview builds (or serves the cached) review report for a match.
//
// Status contract: 503 when POLICY_SERVER_URL is unset (no reviewer
// configured); 404 when no paipu exists for matchId; 422 when the paipu
// can't be reconstructed into reviewable decisions
// (errors.Is(err, review.ErrUnreviewable)); 502 when the policy server call
// itself fails; 200 with the report JSON otherwise.
//
// Cache policy: with a DB present, the newest cached MatchReview for the
// match is returned as-is unless ?force=1 is passed, in which case a fresh
// report is built and upserted keyed on (MatchID, CheckpointID=report's
// serving checkpoint). Without a DB (dev mode), every call builds fresh and
// nothing is cached.
func (s *Server) handlePostReview(c *gin.Context) {
	matchID := c.Param("matchId")
	if matchID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "matchId is required"})
		return
	}

	policyURL := os.Getenv("POLICY_SERVER_URL")
	if policyURL == "" {
		c.JSON(http.StatusServiceUnavailable, gin.H{"error": "reviewer unavailable"})
		return
	}

	force := c.Query("force") == "1"
	if s.DB != nil && !force {
		var cached storage.MatchReview
		err := s.DB.Where("match_id = ?", matchID).Order("created_at DESC").First(&cached).Error
		if err == nil {
			c.Data(http.StatusOK, "application/json", []byte(cached.ReportJSON))
			return
		}
		if !errors.Is(err, gorm.ErrRecordNotFound) {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to check cached review"})
			return
		}
	}

	paipuJSON, ok := s.loadPaipuJSON(matchID)
	if !ok {
		c.JSON(http.StatusNotFound, gin.H{"error": "Match not found"})
		return
	}

	var paipu engine.Paipu
	if err := json.Unmarshal([]byte(paipuJSON), &paipu); err != nil {
		c.JSON(http.StatusUnprocessableEntity, gin.H{"error": "unreviewable paipu: " + err.Error()})
		return
	}

	eventWindow := reviewEventWindow(policyURL)
	report, err := review.BuildReport(&paipu, review.NewHTTPPolicyClient(policyURL, eventWindow), eventWindow)
	if err != nil {
		if errors.Is(err, review.ErrUnreviewable) {
			// Divergence/extraction detail is the whole point of a 422 and
			// contains no internal URLs — keep it in the body.
			c.JSON(http.StatusUnprocessableEntity, gin.H{"error": "unreviewable paipu: " + err.Error()})
			return
		}
		// Policy-server failures embed the internal POLICY_SERVER_URL in the
		// error chain (http.Client errors include the request URL) — log the
		// detail server-side, return a generic body to the caller.
		log.Printf("review: policy server evaluation failed for match %s: %v", matchID, err)
		c.JSON(http.StatusBadGateway, gin.H{"error": "policy server evaluation failed"})
		return
	}

	reportJSON, err := json.Marshal(report)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to encode report"})
		return
	}

	if s.DB != nil {
		if err := s.cacheMatchReview(matchID, report.CheckpointPath, reportJSON); err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to cache review"})
			return
		}
	}

	c.Data(http.StatusOK, "application/json", reportJSON)
}

// cacheMatchReview upserts the MatchReview row keyed on (matchID,
// checkpointID): an existing row for that exact pair is overwritten in
// place (refreshing CreatedAt so it stays "newest"); otherwise a new row is
// inserted. This keeps prior champions' reports around under their own
// CheckpointID while a re-review with the same champion replaces its own
// cache entry rather than accumulating duplicates.
func (s *Server) cacheMatchReview(matchID, checkpointID string, reportJSON []byte) error {
	var existing storage.MatchReview
	err := s.DB.Where("match_id = ? AND checkpoint_id = ?", matchID, checkpointID).First(&existing).Error
	if err == nil {
		existing.ReportJSON = string(reportJSON)
		return s.DB.Save(&existing).Error
	}
	if !errors.Is(err, gorm.ErrRecordNotFound) {
		return err
	}
	row := storage.MatchReview{
		MatchID:      matchID,
		CheckpointID: checkpointID,
		ReportJSON:   string(reportJSON),
	}
	return s.DB.Create(&row).Error
}
