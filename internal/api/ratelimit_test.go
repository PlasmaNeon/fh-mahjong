package api

import (
	"fmt"
	"testing"
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

// The map is keyed by client IP among other things, so a long-lived process
// seeing many distinct callers must not grow without bound.
func TestKeyedRateLimiterPrunesIdleBuckets(t *testing.T) {
	limiter := newKeyedRateLimiter(60, 1)
	for i := 0; i < maxTrackedRateKeys+10; i++ {
		limiter.Allow(fmt.Sprintf("ip:198.51.100.%d", i))
	}
	limiter.mu.Lock()
	size := len(limiter.buckets)
	limiter.mu.Unlock()
	if size > maxTrackedRateKeys {
		t.Fatalf("tracked keys = %d, want at most %d", size, maxTrackedRateKeys)
	}
}
