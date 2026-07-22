package api

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"
	"sync/atomic"
	"time"

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
// equals the resolved RL agent endpoint, via
// remote.EffectiveRLEndpointURLFromEnv() — the SAME fallback chain
// cmd/server's rlEndpointURL applies (RL_AGENT_POLICY_URL, else
// AI_BOT_POLICY_URL, else the local default http://127.0.0.1:8765/act).
//
// Round 11 fix: this used to resolve the RL endpoint locally (RL_AGENT_
// POLICY_URL, else AI_BOT_POLICY_URL, "minus the local-default case") and
// skip the same-service guard whenever that came up empty. But cmd/server
// itself never leaves the RL endpoint unresolved — with both overrides unset
// it still serves RL traffic on the local default. So "both overrides
// unset" isn't "no RL endpoint", it's "RL endpoint is the local default",
// and any POLICY_SERVER_URL naming a different service must still fail
// closed to 0 rather than silently inheriting RL_AGENT_EVENT_WINDOW.
// Resolving through the shared helper (also used by cmd/server) closes that
// gap. Otherwise this fails closed to 0 (event-free) rather than guessing a
// wire contract POLICY_SERVER_URL might not actually speak, the same
// fail-closed contract resolveAIBotEventWindow established in cmd/server for
// the AI_BOT_POLICY_URL/RL_AGENT_POLICY_URL split.
func reviewEventWindow(policyURL string) uint32 {
	if raw := strings.TrimSpace(os.Getenv("REVIEW_EVENT_WINDOW")); raw != "" {
		return parseReviewEventWindowEnv("REVIEW_EVENT_WINDOW", 0)
	}

	effectiveRLURL, _ := remote.EffectiveRLEndpointURLFromEnv()

	if policyURL != "" && !sameReviewService(policyURL, effectiveRLURL) {
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

// handleGetReview serves the review report for a match. It is a pure cache
// lookup — it never builds a report (that remains handlePostReview's job) —
// so it stays public/unauthenticated. DB nil → 404.
//
// Round 23, Finding 1: this used to serve the newest cached MatchReview row
// unconditionally, with no check against what the policy server is actually
// serving right now. That let a promotion/rollback go unnoticed by GET
// callers indefinitely: the cached report from a retired checkpoint kept
// being served as if it were current, and — because Replay.tsx treats ANY
// 200 here as "review ready" — the checkpoint-aware POST path (which DOES
// resolve the live sha) never even ran to correct it.
//
// Fixed the same way handlePostReview already establishes checkpoint
// identity: resolve the live sha via /healthz (through reviewLiveSha's
// short-TTL cache — see reviewShaCacheTTL — so this public route doesn't
// hammer /healthz once per casual page load) and require an EXACT
// (matchID, sha) row:
//
//   - POLICY_SERVER_URL unset (no reviewer configured at all): there is no
//     live checkpoint identity to contradict a cached row, so this keeps the
//     pre-round-23 newest-row fallback unchanged.
//   - healthz unreachable/erroring: FAILS CLOSED — 503, mirroring
//     handlePostReview's round-22 Finding 3 semantics — never silently serve
//     a possibly-stale row when the server's identity is unknown.
//   - healthz OK, no checkpoint_sha256 field (true legacy serve_policy.py):
//     newest-row fallback, same as always.
//   - healthz OK with a sha: ONLY the exact (matchID, sha) row is served; a
//     miss is a 404 so the frontend falls through to its existing
//     "Request review" (POST) flow, which builds fresh (or serves its own
//     cheap cache hit) for the checkpoint actually serving right now.
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

	policyURL := os.Getenv("POLICY_SERVER_URL")
	if policyURL == "" {
		s.serveNewestReview(c, matchID)
		return
	}

	sha, legacy, err := s.reviewLiveSha(c.Request.Context(), policyURL)
	if err != nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{"error": "policy server identity unavailable"})
		return
	}
	if legacy {
		s.serveNewestReview(c, matchID)
		return
	}

	var row storage.MatchReview
	err = s.DB.Where("match_id = ? AND checkpoint_id = ?", matchID, sha).First(&row).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		c.JSON(http.StatusNotFound, gin.H{"error": "no cached review for the current checkpoint"})
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to load cached review"})
		return
	}

	c.Data(http.StatusOK, "application/json", []byte(row.ReportJSON))
}

// serveNewestReview is the pre-round-23 "newest cached row for this match"
// lookup, still used by handleGetReview whenever there is no live checkpoint
// identity to check a row against (no reviewer configured, or a true legacy
// policy server).
func (s *Server) serveNewestReview(c *gin.Context, matchID string) {
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

// reviewLiveSha resolves the policy server's currently-served checkpoint
// identity for GET /matches/:matchId/review (round 23, Finding 1), through a
// short-TTL cache (reviewShaCacheTTL) so this public, unauthenticated route
// doesn't fire a fresh /healthz round trip on every single page load.
//
// Only a SUCCESSFUL resolution is cached: an error is never cached, so a
// transient healthz outage self-heals on the very next request rather than
// pinning every GET to 503 for the rest of the TTL window.
func (s *Server) reviewLiveSha(ctx context.Context, policyURL string) (sha string, legacy bool, err error) {
	s.reviewShaCacheMu.Lock()
	cached := s.reviewShaCache
	s.reviewShaCacheMu.Unlock()
	if cached.policyURL == policyURL && time.Since(cached.fetchedAt) < reviewShaCacheTTL {
		return cached.sha, cached.legacy, nil
	}

	policyClient := review.NewHTTPPolicyClientWithToken(policyURL, 0, os.Getenv("POLICY_SERVER_TOKEN"))
	sha, err = policyClient.CurrentCheckpointSha256(ctx)
	if err != nil {
		return "", false, err
	}
	legacy = sha == ""

	s.reviewShaCacheMu.Lock()
	s.reviewShaCache = reviewShaCacheEntry{policyURL: policyURL, sha: sha, legacy: legacy, fetchedAt: time.Now()}
	s.reviewShaCacheMu.Unlock()

	return sha, legacy, nil
}

// handlePostReview builds (or serves the cached) review report for a match.
//
// Status contract: 503 when POLICY_SERVER_URL is unset (no reviewer
// configured) OR when the policy server's identity can't be established via
// /healthz (round 22, Finding 3 — see below); 429 when the caller's per-user
// rate limit or the server-wide build admission queue is exhausted (round
// 22, Finding 1); 404 when no paipu exists for matchId; 422 when the paipu
// can't be reconstructed into reviewable decisions
// (errors.Is(err, review.ErrUnreviewable)); 502 when the policy server call
// itself fails; 504 if the caller's own request is cancelled/times out while
// waiting on a build that keeps running for other waiters; 200 with the
// report JSON otherwise.
//
// Checkpoint identity (round 21, Finding 2 + round 22, Finding 2/3): every
// call first resolves which checkpoint the policy server is CURRENTLY
// serving via HTTPPolicyClient.CurrentCheckpointSha256.
//
//   - healthz unreachable, erroring, or timing out: FAILS CLOSED — 503,
//     "policy server identity unavailable". Round 21 folded this into the
//     newest-row fallback below; round 22 tightened that, because silently
//     serving a possibly-stale cached row when the server's identity is
//     literally unknown is the whole bug this finding is about. A build
//     that's actually needed will hit the same unreachable server and
//     surface its own error on its own next attempt.
//   - healthz OK but the body has no checkpoint_sha256 field at all (a true
//     legacy serve_policy.py that predates the field): unchanged
//     pre-round-21 behavior — the newest cached MatchReview row for the
//     match, by CreatedAt, is served as-is when one exists.
//   - healthz OK with a sha: the lookup is an EXACT (matchID, sha) row — a
//     hit serves that row as-is (even after other checkpoints have since
//     been reviewed for this match); a miss builds fresh, which records the
//     new row under that same sha (reviewCacheCheckpointID, round 18). This
//     makes a rollback to a previously-reviewed checkpoint re-serve its own
//     old report without rebuilding, and a promotion/reload to a new
//     checkpoint always build fresh rather than serving a stale champion's
//     cached report.
//
// ?force=1 skips the cache lookups above and always builds fresh (and, when
// a sha is known, records the new row under that sha rather than disturbing
// any other champion's row) — but still resolves currentSha first (fails
// closed the same way on a healthz error), since Finding 2 needs it to key
// the build and validate the result below. Without a DB (dev mode), every
// call builds fresh and nothing is cached.
//
// Concurrency and admission (round 21 Findings 1b/1c; round 22 Finding 1):
// building is not done under c directly. Every build (forced, or a cache
// miss) is routed through reviewBuildGroup, an x/sync/singleflight.Group
// keyed on matchID + the resolved checkpoint identity + force-ness (round
// 22, Finding 2 — see buildReviewKey), so concurrent requests that actually
// expect the SAME checkpoint share one in-flight build, while a request that
// resolves a DIFFERENT sha (server promoted/rolled back mid-flight) always
// gets its own build rather than silently coalescing into a stranger's
// result. The build itself runs via DoChan in an independent goroutine with
// its own DETACHED context (buildReviewOutcome's ctx, not c.Request's) —
// this caller (and every other caller sharing the same key) merely SELECTS
// between that goroutine finishing and its own c.Request.Context() being
// cancelled (client disconnected/request timed out): a caller giving up
// early stops waiting (504) without cancelling the shared build for anyone
// else still waiting on it, and the build still completes and caches
// normally. Inside that goroutine, acquireReviewBuildSlot bounds how many
// DIFFERENT checkpoint-builds may run/queue at once server-wide (capacity
// reviewBuildConcurrencyLimit + wait queue reviewBuildWaitQueueLimit); beyond
// that, the build fails immediately with 429 rather than queuing
// unboundedly. A per-user token bucket (reviewRateLimiter) gates entry even
// earlier, before any of this — a spammy caller is turned away before ever
// touching the shared admission queue.
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

	if userIDVal, ok := c.Get("userID"); ok {
		if userID, ok := userIDVal.(uint); ok && !s.reviewRateLimiter.Allow(userID) {
			c.Header("Retry-After", "10")
			c.JSON(http.StatusTooManyRequests, gin.H{"error": "too many review requests, slow down and retry shortly"})
			return
		}
	}

	force := c.Query("force") == "1"
	eventWindow := reviewEventWindow(policyURL)
	// POLICY_SERVER_TOKEN authenticates POST /evaluate (and now GET
	// /healthz's bearer header, harmlessly ignored by servers that don't
	// require auth on /healthz) on policyURL (adversarial round 19): see
	// buildReviewOutcome for the /evaluate failure-mode documentation.
	policyToken := os.Getenv("POLICY_SERVER_TOKEN")
	policyClient := review.NewHTTPPolicyClientWithToken(policyURL, eventWindow, policyToken)

	reqCtx := c.Request.Context()
	currentSha, shaErr := policyClient.CurrentCheckpointSha256(reqCtx)
	if shaErr != nil {
		// Fail closed (round 22, Finding 3): never silently serve a
		// possibly-stale cached row when the server's identity is unknown.
		c.JSON(http.StatusServiceUnavailable, gin.H{"error": "policy server identity unavailable"})
		return
	}
	legacy := currentSha == ""

	if s.DB != nil && !force {
		if !legacy {
			var cached storage.MatchReview
			err := s.DB.Where("match_id = ? AND checkpoint_id = ?", matchID, currentSha).First(&cached).Error
			if err == nil {
				c.Data(http.StatusOK, "application/json", []byte(cached.ReportJSON))
				return
			}
			if !errors.Is(err, gorm.ErrRecordNotFound) {
				c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to check cached review"})
				return
			}
			// Cache miss for the currently-served sha: fall through to a
			// fresh build below, which will record it under currentSha.
		} else {
			// True legacy server (healthz ok, no sha field): today's
			// newest-row fallback.
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
	}

	key := buildReviewKey(matchID, currentSha, legacy, force)
	resultCh := s.reviewBuildGroup.DoChan(key, func() (interface{}, error) {
		return s.buildReviewOutcome(matchID, policyClient, eventWindow, currentSha, legacy), nil
	})

	select {
	case res := <-resultCh:
		outcome := res.Val.(reviewBuildOutcome)
		if outcome.retryAfterSeconds > 0 {
			c.Header("Retry-After", strconv.Itoa(outcome.retryAfterSeconds))
		}
		c.Data(outcome.status, "application/json", outcome.body)
	case <-reqCtx.Done():
		// This caller gave up (client disconnected or request context
		// expired). The build above keeps running in its own goroutine on a
		// detached context — it still completes and caches for whoever else
		// is waiting on the same key (or the next cache hit) — we simply
		// stop waiting on it here.
		c.JSON(http.StatusGatewayTimeout, gin.H{"error": "request cancelled while waiting for review build"})
	}
}

// buildReviewKey is the singleflight key for one review build (round 22,
// Finding 2): matchID alone let a request expecting one checkpoint coalesce
// into another request's in-flight build for a DIFFERENT checkpoint (e.g. a
// promotion/rollback landing between two requests for the same match).
// Folding in the resolved checkpoint identity means two requests only share
// a build when they actually expect the same served bytes; force-ness gets
// its own slot too, so a plain cache-serving request can never coalesce with
// a concurrent forced rebuild (or vice versa) — each stays on its own key.
func buildReviewKey(matchID, currentSha string, legacy, force bool) string {
	shaPart := currentSha
	if legacy {
		shaPart = "<legacy>"
	}
	return fmt.Sprintf("%s|sha=%s|force=%t", matchID, shaPart, force)
}

// reviewBuildOutcome is the fully-resolved HTTP result of one review build
// (status code + JSON body), computed once per singleflight key and handed
// identically to every caller that was waiting on it. retryAfterSeconds is
// non-zero only for a 429 admission rejection (round 22, Finding 1a).
type reviewBuildOutcome struct {
	status            int
	body              []byte
	retryAfterSeconds int
}

func reviewErrorOutcome(status int, msg string) reviewBuildOutcome {
	body, err := json.Marshal(gin.H{"error": msg})
	if err != nil {
		// gin.H{"error": string} always marshals; this is unreachable in
		// practice, but never send a malformed body.
		body = []byte(`{"error":"internal error"}`)
	}
	return reviewBuildOutcome{status: status, body: body}
}

// reviewBuildTimeout bounds a shared review build's detached context (round
// 22, Finding 1c): matches HTTPPolicyClient's own /evaluate client timeout,
// so this is not a NEW ceiling, just where that ceiling is now applied from
// (the build's own goroutine, not any one caller's request).
const reviewBuildTimeout = 120 * time.Second

// errReviewBuildQueueFull is returned by acquireReviewBuildSlot when both the
// concurrency cap and the wait queue are exhausted (round 22, Finding 1a).
var errReviewBuildQueueFull = errors.New("review build queue is full")

// acquireReviewBuildSlot reserves one of reviewBuildConcurrencyLimit
// server-wide build slots, queuing (bounded to reviewBuildWaitQueueLimit
// waiters) if all slots are currently taken. Unlike the round-21 version
// (an unconditional, unbounded blocking send), this never blocks forever
// with no way out: once reviewBuildWaitQueueLimit waiters are already
// queued, a new attempt fails immediately with errReviewBuildQueueFull
// rather than growing the queue further.
func (s *Server) acquireReviewBuildSlot() error {
	select {
	case s.reviewBuildSem <- struct{}{}:
		return nil
	default:
	}

	if atomic.AddInt32(&s.reviewBuildWaiters, 1) > reviewBuildWaitQueueLimit {
		atomic.AddInt32(&s.reviewBuildWaiters, -1)
		return errReviewBuildQueueFull
	}
	defer atomic.AddInt32(&s.reviewBuildWaiters, -1)

	s.reviewBuildSem <- struct{}{}
	return nil
}

// releaseReviewBuildSlot releases a slot acquired by acquireReviewBuildSlot.
func (s *Server) releaseReviewBuildSlot() {
	<-s.reviewBuildSem
}

// buildReviewOutcome does the actual work of building (and, with a DB
// present, caching) a review report for matchID against policyClient.
// Invoked from inside s.reviewBuildGroup.DoChan's own goroutine (round 22,
// Finding 1): that goroutine is independent of any single caller's HTTP
// request, so it runs to completion (and caches its result) even if every
// caller waiting on it gives up. Its own context is DELIBERATELY detached
// from any caller's request context — see handlePostReview's doc — bounded
// only by reviewBuildTimeout, matching HTTPPolicyClient's /evaluate timeout.
//
// expectedSha/legacy are the checkpoint identity resolved by the caller
// BEFORE this build started (used for the singleflight key — see
// buildReviewKey). After a successful build, if expectedSha was known
// (!legacy) and the report itself reports a sha, the two are cross-checked
// (round 22, Finding 2's defense-in-depth on top of the key split above): a
// mismatch means the policy server's identity moved again mid-build, so the
// result is discarded (503) rather than cached/served as if it reflected
// the checkpoint this build was keyed for.
func (s *Server) buildReviewOutcome(matchID string, policyClient *review.HTTPPolicyClient, eventWindow uint32, expectedSha string, legacy bool) reviewBuildOutcome {
	if err := s.acquireReviewBuildSlot(); err != nil {
		outcome := reviewErrorOutcome(http.StatusTooManyRequests, "review build queue is full, retry shortly")
		outcome.retryAfterSeconds = 5
		return outcome
	}
	defer s.releaseReviewBuildSlot()

	paipuJSON, ok := s.loadPaipuJSON(matchID)
	if !ok {
		return reviewErrorOutcome(http.StatusNotFound, "Match not found")
	}

	var paipu engine.Paipu
	if err := json.Unmarshal([]byte(paipuJSON), &paipu); err != nil {
		return reviewErrorOutcome(http.StatusUnprocessableEntity, "unreviewable paipu: "+err.Error())
	}

	ctx, cancel := context.WithTimeout(context.Background(), reviewBuildTimeout)
	defer cancel()

	report, err := review.BuildReport(ctx, &paipu, policyClient, eventWindow)
	if err != nil {
		if errors.Is(err, review.ErrUnreviewable) {
			// Divergence/extraction detail is the whole point of a 422 and
			// contains no internal URLs — keep it in the body.
			return reviewErrorOutcome(http.StatusUnprocessableEntity, "unreviewable paipu: "+err.Error())
		}
		// Policy-server failures embed the internal POLICY_SERVER_URL in the
		// error chain (http.Client errors include the request URL) — log the
		// detail server-side, return a generic body to the caller.
		log.Printf("review: policy server evaluation failed for match %s: %v", matchID, err)
		return reviewErrorOutcome(http.StatusBadGateway, "policy server evaluation failed")
	}

	// Round 23, Finding 2: when a live sha WAS expected (!legacy,
	// expectedSha != ""), the build's report must carry that SAME sha — not
	// just "a different non-empty one". The pre-round-23 guard only ever
	// compared two non-empty shas, so a build whose /evaluate response
	// simply OMITTED checkpoint_sha256 (a rolling deploy or proxy briefly
	// routing to a stale/mismatched instance) sailed through this check
	// (report.CheckpointSha256 == "" short-circuited it) and got cached and
	// served under expectedSha as if it genuinely reflected that checkpoint.
	// Requiring an exact, non-empty match whenever a sha was expected closes
	// that gap: "missing" is treated exactly like "different", not like
	// "legacy/unknown".
	if !legacy && expectedSha != "" && report.CheckpointSha256 != expectedSha {
		log.Printf("review: match %s expected checkpoint %s but build reported %q; policy server identity moved (or omitted its sha) mid-build, discarding result", matchID, expectedSha, report.CheckpointSha256)
		return reviewErrorOutcome(http.StatusServiceUnavailable, "policy server checkpoint changed during review build; retry")
	}

	reportJSON, err := json.Marshal(report)
	if err != nil {
		return reviewErrorOutcome(http.StatusInternalServerError, "failed to encode report")
	}

	if s.DB != nil {
		if err := s.cacheMatchReview(matchID, reviewCacheCheckpointID(report), reportJSON); err != nil {
			return reviewErrorOutcome(http.StatusInternalServerError, "failed to cache review")
		}
	}

	return reviewBuildOutcome{status: http.StatusOK, body: reportJSON}
}

// reviewCacheCheckpointID picks the cache identity for report: its
// CheckpointSha256 when the serving policy reported one, else its
// CheckpointPath (round 18 fix).
//
// CheckpointPath alone survives a same-path hot reload — a checkpoint file
// overwritten in place still has the same path but different bytes/decisions
// — so keying the cache on path collapses two distinct served checkpoints
// into one row: a non-forced request would then serve stale bytes' report as
// if it were current, and a forced refresh would destroy the old bytes'
// report by overwriting that same row. CheckpointSha256 is the content hash
// of the checkpoint that actually produced the report (see Report's doc), so
// it survives the reload and gives each distinct set of served bytes its own
// row.
//
// CheckpointSha256 is only populated by serve_policy.py builds that support
// it (round 17); a legacy sha-less server reports "" here, in which case
// this falls back to CheckpointPath, preserving today's behavior exactly —
// no regression for deployments that haven't upgraded the policy server.
func reviewCacheCheckpointID(report *review.Report) string {
	if report.CheckpointSha256 != "" {
		return report.CheckpointSha256
	}
	return report.CheckpointPath
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
