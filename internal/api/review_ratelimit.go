package api

import (
	"sync"
	"time"
)

// reviewRateLimitPerMinute/reviewRateLimitBurst bound how often ONE
// authenticated user may trigger a review build (adversarial round 22,
// Finding 1d). Deliberately tiny and fixed, mirroring
// reviewBuildConcurrencyLimit's philosophy: review builds are a
// debugging/analysis path, never meant to be hammered, so a generous
// interactive user (a handful of distinct-match reviews in a burst, or a
// couple of retries) sails through while an automated spam loop is turned
// away well before it can queue up any real work.
const (
	reviewRateLimitPerMinute = 6.0
	reviewRateLimitBurst     = 6.0
)

// reviewRateBucket is one user's token bucket.
type reviewRateBucket struct {
	tokens     float64
	lastRefill time.Time
}

// reviewRateLimiter is a tiny in-memory per-user token bucket guarding POST
// /matches/:matchId/review (adversarial round 22, Finding 1d). It is
// intentionally NOT a general-purpose rate limiter package: no persistence,
// no distributed coordination — matching this repo's single-process
// deployment model (see the in-process matchmaking queue). Restarting the
// process resets every bucket, which is fine: the goal is smoothing one
// browser tab's request storm, not a hard security boundary.
type reviewRateLimiter struct {
	mu      sync.Mutex
	buckets map[uint]*reviewRateBucket
}

func newReviewRateLimiter() *reviewRateLimiter {
	return &reviewRateLimiter{buckets: make(map[uint]*reviewRateBucket)}
}

// Allow reports whether userID may make one more review-build request right
// now, consuming a token if so. Safe for concurrent use.
func (l *reviewRateLimiter) Allow(userID uint) bool {
	l.mu.Lock()
	defer l.mu.Unlock()

	now := time.Now()
	b, ok := l.buckets[userID]
	if !ok {
		b = &reviewRateBucket{tokens: reviewRateLimitBurst, lastRefill: now}
		l.buckets[userID] = b
	}

	elapsed := now.Sub(b.lastRefill).Seconds()
	if elapsed > 0 {
		b.tokens += elapsed * (reviewRateLimitPerMinute / 60.0)
		if b.tokens > reviewRateLimitBurst {
			b.tokens = reviewRateLimitBurst
		}
		b.lastRefill = now
	}

	if b.tokens < 1 {
		return false
	}
	b.tokens -= 1
	return true
}
