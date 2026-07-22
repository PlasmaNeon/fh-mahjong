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
	"gorm.io/gorm/clause"
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
//
// Round 24, Finding 1: before ANY of the above (in particular, before ever
// resolving the live checkpoint sha via healthz), this now checks whether a
// MatchReview row exists for matchID AT ALL. A match nobody has ever
// reviewed can never turn into a 200 regardless of what the live sha turns
// out to be, so there is nothing to gain — and policy-server/healthz load to
// lose — by resolving it first. This closes the amplification an
// unauthenticated caller could otherwise drive: hammering GET for arbitrary
// (including nonexistent) match ids used to fire a healthz round trip per
// request once any cached entry expired.
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

	hasCached, err := s.matchHasAnyCachedReview(matchID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to check cached review"})
		return
	}
	if !hasCached {
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

// matchHasAnyCachedReview reports whether ANY MatchReview row exists for
// matchID, regardless of checkpoint identity (round 24, Finding 1). This is
// deliberately checked before handleGetReview ever contacts the policy
// server's /healthz: a match with zero cached rows can never resolve to a
// 200 no matter what the live checkpoint turns out to be, so there is no
// reason to spend a healthz round trip finding that out.
func (s *Server) matchHasAnyCachedReview(matchID string) (bool, error) {
	var count int64
	err := s.DB.Model(&storage.MatchReview{}).Where("match_id = ?", matchID).Count(&count).Error
	if err != nil {
		return false, err
	}
	return count > 0, nil
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
// Round 24, Finding 1 hardened this in two ways, on top of round 23's cache:
//
//   - Coalescing: once a cached entry is stale (or was never populated), the
//     actual refresh is routed through reviewShaGroup, keyed on policyURL.
//     Concurrent callers observing the same stale/missing entry share ONE
//     healthz call and one result rather than each firing their own — this
//     is what actually bounds healthz load under concurrent GET traffic,
//     the cache mutex alone only ever protected the cached COPY, not the
//     refresh itself.
//   - Negative caching: a FAILED resolution is now cached too (as
//     reviewShaCacheEntry.err), for the much shorter reviewShaNegativeCacheTTL.
//     Without this, a healthz outage meant every single GET (not just
//     concurrent ones — sequential ones too) re-attempted healthz, each
//     paying its own timeout. The negative TTL is short enough that a real
//     recovery is still picked up promptly, but long enough that a burst or
//     a steady trickle of GETs during an outage collapses onto one attempt
//     per window instead of one attempt per request.
func (s *Server) reviewLiveSha(ctx context.Context, policyURL string) (sha string, legacy bool, err error) {
	if entry, ok := s.cachedReviewSha(policyURL); ok {
		return entry.sha, entry.legacy, entry.err
	}

	// singleflight.Group.Do blocks every concurrent caller sharing this key
	// until the first caller's function returns, then hands all of them the
	// SAME (value, error) — this is what turns "N concurrent callers each
	// see a stale cache" into "N concurrent callers, one healthz call".
	//
	// The healthz call itself runs on a context detached from any single
	// caller's request (context.Background(), bounded only by
	// CurrentCheckpointSha256's own internal reviewHealthzTimeout): ctx here
	// is only the FIRST caller's request context, and that caller giving up
	// (client disconnect / its own request timeout) must never cut the
	// shared call short for every other caller waiting on the same result.
	result, resultErr, _ := s.reviewShaGroup.Do(policyURL, func() (interface{}, error) {
		policyClient := review.NewHTTPPolicyClientWithToken(policyURL, 0, os.Getenv("POLICY_SERVER_TOKEN"))
		sha, err := policyClient.CurrentCheckpointSha256(context.Background())

		entry := reviewShaCacheEntry{policyURL: policyURL, fetchedAt: time.Now()}
		if err != nil {
			entry.err = err
		} else {
			entry.sha = sha
			entry.legacy = sha == ""
		}

		s.reviewShaCacheMu.Lock()
		s.reviewShaCache = entry
		s.reviewShaCacheMu.Unlock()

		if err != nil {
			return nil, err
		}
		return entry, nil
	})
	_ = ctx // retained in the signature; the shared call itself never uses a per-caller context (see above).
	if resultErr != nil {
		return "", false, resultErr
	}
	entry := result.(reviewShaCacheEntry)
	return entry.sha, entry.legacy, nil
}

// cachedReviewSha returns the currently cached entry for policyURL, if it is
// still fresh enough to trust: a successful entry within reviewShaCacheTTL,
// or a failed entry within the shorter reviewShaNegativeCacheTTL (round 24,
// Finding 1). ok is false whenever the entry is for a different policyURL,
// missing, or expired — the caller must then refresh (via reviewShaGroup).
func (s *Server) cachedReviewSha(policyURL string) (reviewShaCacheEntry, bool) {
	s.reviewShaCacheMu.Lock()
	cached := s.reviewShaCache
	s.reviewShaCacheMu.Unlock()

	if cached.policyURL != policyURL {
		return reviewShaCacheEntry{}, false
	}
	age := time.Since(cached.fetchedAt)
	if cached.err != nil {
		return cached, age < reviewShaNegativeCacheTTL
	}
	return cached, age < reviewShaCacheTTL
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
// Concurrency and admission (round 21 Findings 1b/1c; round 22 Finding 1;
// round 25 Findings 1/2): building is not done under c directly. Every build
// (forced, or a cache miss) is routed through reviewBuildGroup, an
// x/sync/singleflight.Group keyed on matchID + the resolved checkpoint
// identity (buildReviewKey) — NOT force-ness (round 25, Finding 2: see
// buildReviewKey's doc for why folding force into the key was actively
// harmful) — so concurrent requests that actually expect the SAME checkpoint
// share one in-flight build, while a request that resolves a DIFFERENT sha
// (server promoted/rolled back mid-flight) always gets its own build rather
// than silently coalescing into a stranger's result.
//
// The build itself runs via DoChan in an independent goroutine against ONE
// bounded, detached context created BEFORE queue admission (round 25,
// Finding 1: reviewBuildTotalTimeout, context.Background() bounded by the
// WHOLE build lifecycle — semaphore wait, paipu load, evaluation, and
// persistence — not just the /evaluate call). This closes a wedge: previously
// the semaphore acquisition blocked with no deadline at all, and the
// timeout only wrapped the /evaluate call itself (established well AFTER
// admission and after the contextless paipu-load DB queries) — a stall
// anywhere before that point (a hung DB call, in particular) held a build
// slot forever, and once both reviewBuildConcurrencyLimit slots were wedged
// that way every subsequent request piled into the wait queue and then
// started 429ing permanently. Now acquireReviewBuildSlot itself selects on
// this same ctx while waiting for a slot (timeout → 503, slot cleanly
// released, no wedge), and loadPaipuJSON's DB calls run under
// DB.WithContext(ctx) so a stalled query is bounded too.
//
// This caller (and every other caller sharing the same key) merely SELECTS
// between that goroutine finishing and its own c.Request.Context() being
// cancelled (client disconnected/request timed out): a caller giving up
// early stops waiting (504) without cancelling the shared build for anyone
// else still waiting on it, and the build still completes (up to its own
// bounded ctx) and caches normally. Inside that goroutine,
// acquireReviewBuildSlot bounds how many DIFFERENT checkpoint-builds may
// run/queue at once server-wide (capacity reviewBuildConcurrencyLimit + wait
// queue reviewBuildWaitQueueLimit); beyond that, the build fails immediately
// with 429 rather than queuing unboundedly. A per-user token bucket
// (reviewRateLimiter) gates entry even earlier, before any of this — a
// spammy caller is turned away before ever touching the shared admission
// queue.
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

	key := buildReviewKey(matchID, currentSha, legacy)
	resultCh := s.reviewBuildGroup.DoChan(key, func() (interface{}, error) {
		// Round 25, Finding 1: ONE detached-but-bounded context for the whole
		// build lifecycle — created here, before admission is ever attempted
		// — shared by every caller coalesced onto this singleflight key. See
		// handlePostReview's concurrency doc above and reviewBuildTotalTimeout.
		buildCtx, cancel := context.WithTimeout(context.Background(), reviewBuildTotalTimeout)
		defer cancel()
		return s.buildReviewOutcome(buildCtx, matchID, policyClient, eventWindow, currentSha, legacy), nil
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
// a build when they actually expect the same served bytes.
//
// Round 25, Finding 2 REMOVED force-ness from this key. Folding it in used
// to give a forced rebuild and a concurrent non-forced cache-miss request
// for the SAME (matchID, sha) their own separate keys — meaning they ran two
// independent builds that both raced to persist the exact same
// (match_id, checkpoint_id) row via cacheMatchReview's old
// First-then-Create: the loser hit the row's unique index and got a bare 500
// despite the winner's build being a perfectly valid, cacheable report for
// that same identity. Dropping force from the key is semantically fine
// because a NON-forced request only ever reaches this build path on a cache
// miss (handlePostReview's cache lookup above already short-circuited any
// non-forced cache HIT) — by the time either request gets here, both already
// want "the freshest build for this exact checkpoint", force or not, so
// coalescing them onto one build is correct, not just convenient. (Combined
// with cacheMatchReview's upsert below, even if two builds somehow still ran
// for the same identity, persistence itself is now race-safe too.)
func buildReviewKey(matchID, currentSha string, legacy bool) string {
	shaPart := currentSha
	if legacy {
		shaPart = "<legacy>"
	}
	return fmt.Sprintf("%s|sha=%s", matchID, shaPart)
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

// reviewBuildTotalTimeout bounds ONE shared review build's ENTIRE lifecycle
// (round 25, Finding 1): semaphore wait + paipu load + policy evaluation +
// persistence, all under a single context created before admission is even
// attempted (see handlePostReview). This replaces the round-22 version,
// which only wrapped the /evaluate call — established well after admission
// and after loadPaipuJSON's then-contextless DB queries — leaving the
// semaphore acquire and the paipu load completely unbounded. Sized as
// HTTPPolicyClient's own /evaluate timeout (120s) plus margin for the paipu
// load and persistence steps that now share the same bound.
//
// A var, not a const, so tests can shrink it to exercise the timeout path
// without an actual multi-second wait.
var reviewBuildTotalTimeout = 150 * time.Second

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
//
// Round 25, Finding 1: the queued wait itself is now also bounded — it
// selects on ctx.Done() (the build's whole-lifecycle bounded context)
// alongside the semaphore send, so a waiter that's about to blow the total
// build budget gives up its queue position and returns ctx.Err() instead of
// blocking indefinitely (or until process exit) for a slot that a wedged
// build ahead of it may never release.
func (s *Server) acquireReviewBuildSlot(ctx context.Context) error {
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

	select {
	case s.reviewBuildSem <- struct{}{}:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
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
// caller waiting on it gives up.
//
// ctx is the ONE detached-but-bounded context created by the caller
// (handlePostReview) BEFORE queue admission was ever attempted (round 25,
// Finding 1) — it bounds admission (acquireReviewBuildSlot), the paipu load,
// the policy evaluation, and persistence uniformly, so a stall in any one of
// those steps can never hold a build slot (and therefore both of them,
// server-wide) open forever. It is DELIBERATELY detached from any caller's
// own HTTP request context — see handlePostReview's doc.
//
// expectedSha/legacy are the checkpoint identity resolved by the caller
// BEFORE this build started (used for the singleflight key — see
// buildReviewKey). After a successful build, if expectedSha was known
// (!legacy) and the report itself reports a sha, the two are cross-checked
// (round 22, Finding 2's defense-in-depth on top of the key split above): a
// mismatch means the policy server's identity moved again mid-build, so the
// result is discarded (503) rather than cached/served as if it reflected
// the checkpoint this build was keyed for.
func (s *Server) buildReviewOutcome(ctx context.Context, matchID string, policyClient *review.HTTPPolicyClient, eventWindow uint32, expectedSha string, legacy bool) reviewBuildOutcome {
	if err := s.acquireReviewBuildSlot(ctx); err != nil {
		if errors.Is(err, errReviewBuildQueueFull) {
			outcome := reviewErrorOutcome(http.StatusTooManyRequests, "review build queue is full, retry shortly")
			outcome.retryAfterSeconds = 5
			return outcome
		}
		// ctx expired (or was cancelled) while queued for a slot (round 25,
		// Finding 1): the wait itself blew the whole-lifecycle build budget,
		// so this attempt gives up rather than blocking indefinitely behind
		// a build that may be wedged. The slot was never acquired, so
		// nothing to release here.
		return reviewErrorOutcome(http.StatusServiceUnavailable, "review build timed out waiting for a slot, retry shortly")
	}
	defer s.releaseReviewBuildSlot()

	paipuJSON, ok := s.loadPaipuJSON(ctx, matchID)
	if !ok {
		return reviewErrorOutcome(http.StatusNotFound, "Match not found")
	}

	var paipu engine.Paipu
	if err := json.Unmarshal([]byte(paipuJSON), &paipu); err != nil {
		return reviewErrorOutcome(http.StatusUnprocessableEntity, "unreviewable paipu: "+err.Error())
	}

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
		if err := s.cacheMatchReview(ctx, matchID, reviewCacheCheckpointID(report), reportJSON); err != nil {
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
//
// Round 25, Finding 2: this used to be a First-then-Create — read the row,
// and if absent, insert one. That has a race window: two builds for the
// SAME (matchID, checkpointID) (previously possible because force-ness was
// folded into the singleflight key — see buildReviewKey's doc) could both
// observe "not found" and both attempt Create, and the loser hit the
// unique index (idx_match_reviews_match_ckpt) and returned a bare error —
// a 500 despite the winner having produced a perfectly valid, cacheable
// report for that exact identity. Now this is a single atomic upsert via
// clause.OnConflict: whichever build's Create reaches the DB first inserts
// the row, and any other build for the same identity (concurrent, or a
// later legitimate re-review) updates it in place instead of erroring —
// there is no read-then-write gap for a second writer to race into.
func (s *Server) cacheMatchReview(ctx context.Context, matchID, checkpointID string, reportJSON []byte) error {
	row := storage.MatchReview{
		MatchID:      matchID,
		CheckpointID: checkpointID,
		ReportJSON:   string(reportJSON),
		CreatedAt:    time.Now(),
	}
	return s.DB.WithContext(ctx).Clauses(clause.OnConflict{
		Columns:   []clause.Column{{Name: "match_id"}, {Name: "checkpoint_id"}},
		DoUpdates: clause.AssignmentColumns([]string{"report_json", "created_at"}),
	}).Create(&row).Error
}
