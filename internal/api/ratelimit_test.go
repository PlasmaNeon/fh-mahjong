package api

import (
	"fmt"
	"testing"
	"time"
)

func TestKeyedRateLimiterSpendsBurstThenRefuses(t *testing.T) {
	limiter := newKeyedRateLimiter(60, 3)
	for i := 0; i < 3; i++ {
		if !limiter.Allow("ip:203.0.113.7") {
			t.Fatalf("request %d within burst was refused", i+1)
		}
	}
	if limiter.Allow("ip:203.0.113.7") {
		t.Fatal("request beyond the burst must be refused")
	}
}

func TestKeyedRateLimiterIsolatesKeys(t *testing.T) {
	limiter := newKeyedRateLimiter(60, 1)
	if !limiter.Allow("user:1") {
		t.Fatal("first key refused")
	}
	if !limiter.Allow("user:2") {
		t.Fatal("a different key must have its own bucket")
	}
	if limiter.Allow("user:1") {
		t.Fatal("the exhausted key must stay refused")
	}
}

// Idle buckets are reclaimed once they would have refilled to full.
func TestKeyedRateLimiterPrunesIdleBuckets(t *testing.T) {
	limiter := newKeyedRateLimiter(60, 1)
	for i := 0; i < maxTrackedRateKeys; i++ {
		limiter.Allow(fmt.Sprintf("ip:198.51.100.%d", i))
	}

	// Age every bucket well past a full refill, standing in for callers who
	// made one request and went away.
	limiter.mu.Lock()
	stale := time.Now().Add(-time.Hour)
	for _, bucket := range limiter.buckets {
		bucket.lastRefill = stale
	}
	limiter.mu.Unlock()

	// A new key crosses the reclaim threshold and triggers the sweep.
	limiter.Allow("ip:203.0.113.1")

	limiter.mu.Lock()
	size := len(limiter.buckets)
	limiter.mu.Unlock()
	if size != 1 {
		t.Fatalf("tracked keys = %d, want 1 (every idle bucket reclaimed)", size)
	}
}

// A bucket whose tokens are spent is live state. Under a flood of distinct
// keys arriving faster than they refill, the map exceeds maxTrackedRateKeys
// rather than forgetting who is being limited.
func TestKeyedRateLimiterKeepsSpentBucketsOverTheCap(t *testing.T) {
	limiter := newKeyedRateLimiter(60, 1)
	for i := 0; i < maxTrackedRateKeys+10; i++ {
		limiter.Allow(fmt.Sprintf("ip:198.51.100.%d", i))
	}

	limiter.mu.Lock()
	size := len(limiter.buckets)
	limiter.mu.Unlock()
	if size != maxTrackedRateKeys+10 {
		t.Fatalf("tracked keys = %d, want all %d retained", size, maxTrackedRateKeys+10)
	}
	if limiter.Allow("ip:198.51.100.0") {
		t.Fatal("a spent bucket must stay refused — dropping it would grant a fresh burst")
	}
}
