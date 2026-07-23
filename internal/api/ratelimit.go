package api

import (
	"sync"
	"time"
)

// maxTrackedRateKeys bounds the bucket map. Keys include client IPs, so a
// long-running process can otherwise accumulate one entry per caller
// indefinitely. When the map crosses this size, buckets that have refilled to
// full (i.e. their owner has gone quiet) are dropped — dropping a full bucket
// is free, because recreating it yields the same full bucket.
const maxTrackedRateKeys = 4096

type rateBucket struct {
	tokens     float64
	lastRefill time.Time
}

// keyedRateLimiter is an in-memory token bucket keyed by an arbitrary string,
// so one limiter can cover several dimensions at once (per-IP and per-user,
// say) by namespacing its keys.
//
// Like reviewRateLimiter, which predates it, this is intentionally not a
// general-purpose package: no persistence and no cross-process coordination,
// matching this repo's single-process deployment. A restart resets every
// bucket, which is fine — the goal is smoothing request storms, not enforcing
// a hard security boundary.
type keyedRateLimiter struct {
	mu        sync.Mutex
	perMinute float64
	burst     float64
	buckets   map[string]*rateBucket
}

func newKeyedRateLimiter(perMinute, burst float64) *keyedRateLimiter {
	return &keyedRateLimiter{
		perMinute: perMinute,
		burst:     burst,
		buckets:   make(map[string]*rateBucket),
	}
}

// Allow reports whether key may act once more right now, consuming a token if
// so. Safe for concurrent use.
func (l *keyedRateLimiter) Allow(key string) bool {
	l.mu.Lock()
	defer l.mu.Unlock()

	now := time.Now()
	bucket, ok := l.buckets[key]
	if !ok {
		if len(l.buckets) >= maxTrackedRateKeys {
			l.pruneFullLocked(now)
		}
		bucket = &rateBucket{tokens: l.burst, lastRefill: now}
		l.buckets[key] = bucket
	}

	if elapsed := now.Sub(bucket.lastRefill).Seconds(); elapsed > 0 {
		bucket.tokens += elapsed * (l.perMinute / 60.0)
		if bucket.tokens > l.burst {
			bucket.tokens = l.burst
		}
		bucket.lastRefill = now
	}

	if bucket.tokens < 1 {
		return false
	}
	bucket.tokens -= 1
	return true
}

// pruneFullLocked drops every bucket that has refilled to capacity. The caller
// must hold l.mu.
func (l *keyedRateLimiter) pruneFullLocked(now time.Time) {
	for key, bucket := range l.buckets {
		tokens := bucket.tokens + now.Sub(bucket.lastRefill).Seconds()*(l.perMinute/60.0)
		if tokens >= l.burst {
			delete(l.buckets, key)
		}
	}
}
