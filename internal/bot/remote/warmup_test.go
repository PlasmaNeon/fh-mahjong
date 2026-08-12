package remote

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func warmupOKBody() string {
	return `{"warmed":true,"checkpoint_path":"/ckpt/iter_075.pt","checkpoint_step":75,` +
		`"checkpoint_sha256":"abc123","contract_version":1,"event_window":128,"latency_ms":42.5}`
}

func TestDeriveWarmupURL(t *testing.T) {
	cases := map[string]string{
		"http://localhost:8765/act":       "http://localhost:8765/warmup",
		"https://policy.example.com/act":  "https://policy.example.com/warmup",
		"http://localhost:8765/act?x=1#y": "http://localhost:8765/warmup",
		"":                                "",
		"not-a-url":                       "",
	}
	for in, want := range cases {
		if got := deriveWarmupURL(in); got != want {
			t.Errorf("deriveWarmupURL(%q) = %q, want %q", in, got, want)
		}
	}
}

func TestWarmupSuccessIsWarmOnce(t *testing.T) {
	var hits atomic.Int64
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/warmup" {
			t.Errorf("unexpected path %q", r.URL.Path)
		}
		if r.Method != http.MethodPost {
			t.Errorf("method = %q, want POST", r.Method)
		}
		hits.Add(1)
		fmt.Fprint(w, warmupOKBody())
	}))
	defer server.Close()

	manager := NewWarmupManager(server.Client())
	endpoint := server.URL + "/act"
	if err := manager.Warm(context.Background(), endpoint, ""); err != nil {
		t.Fatalf("first Warm: %v", err)
	}
	if !manager.Warmed(endpoint) {
		t.Fatal("endpoint should be warm after a successful warmup")
	}
	if err := manager.Warm(context.Background(), endpoint, ""); err != nil {
		t.Fatalf("second Warm: %v", err)
	}
	if got := hits.Load(); got != 1 {
		t.Fatalf("HTTP hits = %d, want 1 (warm once per process)", got)
	}
}

func TestWarmupPerEndpointScope(t *testing.T) {
	var hits atomic.Int64
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hits.Add(1)
		fmt.Fprint(w, warmupOKBody())
	}))
	defer server.Close()
	other := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hits.Add(1)
		fmt.Fprint(w, warmupOKBody())
	}))
	defer other.Close()

	manager := NewWarmupManager(server.Client())
	if err := manager.Warm(context.Background(), server.URL+"/act", ""); err != nil {
		t.Fatalf("warm primary: %v", err)
	}
	if err := manager.Warm(context.Background(), other.URL+"/act", ""); err != nil {
		t.Fatalf("warm shadow: %v", err)
	}
	if got := hits.Load(); got != 2 {
		t.Fatalf("HTTP hits = %d, want 2 (state is endpoint-scoped)", got)
	}
	if manager.Warmed("http://127.0.0.1:1/act") {
		t.Fatal("an unwarmed endpoint must not report warm")
	}
}

func TestWarmupFailureIsRetryable(t *testing.T) {
	var hits atomic.Int64
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if hits.Add(1) == 1 {
			w.WriteHeader(http.StatusInternalServerError)
			fmt.Fprint(w, "boom")
			return
		}
		fmt.Fprint(w, warmupOKBody())
	}))
	defer server.Close()

	manager := NewWarmupManager(server.Client())
	endpoint := server.URL + "/act"
	err := manager.Warm(context.Background(), endpoint, "")
	if err == nil {
		t.Fatal("expected first warmup to fail on 500")
	}
	if !strings.Contains(err.Error(), "500") {
		t.Errorf("error = %v, want it to mention the status", err)
	}
	if manager.Warmed(endpoint) {
		t.Fatal("a failed warmup must leave the endpoint cold")
	}
	if err := manager.Warm(context.Background(), endpoint, ""); err != nil {
		t.Fatalf("retry after failure: %v", err)
	}
	if got := hits.Load(); got != 2 {
		t.Fatalf("HTTP hits = %d, want 2 (failure retried, not latched)", got)
	}
}

func TestWarmupRejectsWarmedFalse(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprint(w, `{"warmed":false}`)
	}))
	defer server.Close()

	manager := NewWarmupManager(server.Client())
	endpoint := server.URL + "/act"
	if err := manager.Warm(context.Background(), endpoint, ""); err == nil {
		t.Fatal("expected warmed=false to be an error")
	}
	if manager.Warmed(endpoint) {
		t.Fatal("warmed=false must not mark the endpoint warm")
	}
}

func TestWarmupRejectsBadJSON(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprint(w, "<html>not json</html>")
	}))
	defer server.Close()

	manager := NewWarmupManager(server.Client())
	if err := manager.Warm(context.Background(), server.URL+"/act", ""); err == nil {
		t.Fatal("expected non-JSON body to be an error")
	}
}

func TestWarmupCoalescesConcurrentCalls(t *testing.T) {
	var hits atomic.Int64
	release := make(chan struct{})
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hits.Add(1)
		<-release
		fmt.Fprint(w, warmupOKBody())
	}))
	defer server.Close()

	manager := NewWarmupManager(server.Client())
	endpoint := server.URL + "/act"

	const callers = 8
	errs := make([]error, callers)
	var started sync.WaitGroup
	var done sync.WaitGroup
	started.Add(callers)
	done.Add(callers)
	for i := 0; i < callers; i++ {
		go func(i int) {
			defer done.Done()
			started.Done()
			errs[i] = manager.Warm(context.Background(), endpoint, "")
		}(i)
	}
	started.Wait()
	// Give the followers a moment to attach to the leader's in-flight call
	// before the server responds, so coalescing is actually exercised.
	time.Sleep(50 * time.Millisecond)
	close(release)
	done.Wait()

	for i, err := range errs {
		if err != nil {
			t.Errorf("caller %d: %v", i, err)
		}
	}
	if got := hits.Load(); got != 1 {
		t.Fatalf("HTTP hits = %d, want 1 (concurrent warmups coalesce)", got)
	}
}

func TestWarmupSendsBearerTokenOnlyWhenProvided(t *testing.T) {
	var gotAuth atomic.Value
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotAuth.Store(r.Header.Get("Authorization"))
		fmt.Fprint(w, warmupOKBody())
	}))
	defer server.Close()

	manager := NewWarmupManager(server.Client())
	if err := manager.Warm(context.Background(), server.URL+"/act", "s3cret"); err != nil {
		t.Fatalf("Warm with token: %v", err)
	}
	if got := gotAuth.Load(); got != "Bearer s3cret" {
		t.Fatalf("Authorization = %q, want %q", got, "Bearer s3cret")
	}

	// A different endpoint (fresh state) with no token must send no header at
	// all — the primary production service runs tokenless.
	tokenless := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotAuth.Store(r.Header.Get("Authorization"))
		fmt.Fprint(w, warmupOKBody())
	}))
	defer tokenless.Close()
	if err := manager.Warm(context.Background(), tokenless.URL+"/act", ""); err != nil {
		t.Fatalf("Warm without token: %v", err)
	}
	if got := gotAuth.Load(); got != "" {
		t.Fatalf("Authorization = %q, want no header", got)
	}
}

func TestWarmupTTLReWarms(t *testing.T) {
	var hits atomic.Int64
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hits.Add(1)
		fmt.Fprint(w, warmupOKBody())
	}))
	defer server.Close()

	manager := NewWarmupManager(server.Client()).WithWarmupTTL(20 * time.Millisecond)
	endpoint := server.URL + "/act"
	if err := manager.Warm(context.Background(), endpoint, ""); err != nil {
		t.Fatalf("first Warm: %v", err)
	}
	if err := manager.Warm(context.Background(), endpoint, ""); err != nil {
		t.Fatalf("second Warm: %v", err)
	}
	if got := hits.Load(); got != 1 {
		t.Fatalf("HTTP hits within TTL = %d, want 1", got)
	}
	time.Sleep(40 * time.Millisecond)
	if manager.Warmed(endpoint) {
		t.Fatal("endpoint should be cold again once the TTL expired")
	}
	if err := manager.Warm(context.Background(), endpoint, ""); err != nil {
		t.Fatalf("post-TTL Warm: %v", err)
	}
	if got := hits.Load(); got != 2 {
		t.Fatalf("HTTP hits after TTL = %d, want 2", got)
	}
}

// TestWarmupHonorsTimeout uses a short client timeout (the 10s production
// budget's fast stand-in) against a server that never responds, so the warmup
// fails on its own budget rather than hanging the admission path.
func TestWarmupHonorsTimeout(t *testing.T) {
	block := make(chan struct{})
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		<-block
	}))
	defer server.Close()
	defer close(block)

	client := server.Client()
	client.Timeout = 50 * time.Millisecond
	manager := NewWarmupManager(client)
	endpoint := server.URL + "/act"

	start := time.Now()
	err := manager.Warm(context.Background(), endpoint, "")
	if err == nil {
		t.Fatal("expected a timeout error")
	}
	if elapsed := time.Since(start); elapsed > 5*time.Second {
		t.Fatalf("warmup took %v, want it bounded by the client timeout", elapsed)
	}
	if manager.Warmed(endpoint) {
		t.Fatal("a timed-out warmup must leave the endpoint cold")
	}
}

// TestWarmupHonorsCallerContext proves the caller's deadline wins even when the
// warmup budget is larger.
func TestWarmupHonorsCallerContext(t *testing.T) {
	block := make(chan struct{})
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		<-block
	}))
	defer server.Close()
	defer close(block)

	manager := NewWarmupManager(server.Client())
	callCtx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()
	if err := manager.Warm(callCtx, server.URL+"/act", ""); err == nil {
		t.Fatal("expected the caller's context deadline to abort the warmup")
	}
}

func TestWarmupRejectsBadEndpoints(t *testing.T) {
	manager := NewWarmupManager(nil)
	if err := manager.Warm(context.Background(), "", ""); err == nil {
		t.Error("empty endpoint should error")
	}
	if err := manager.Warm(context.Background(), "not-a-url", ""); err == nil {
		t.Error("underivable endpoint should error")
	}
	var nilManager *WarmupManager
	if err := nilManager.Warm(context.Background(), "http://x/act", ""); err == nil {
		t.Error("nil manager must fail closed")
	}
	if nilManager.Warmed("http://x/act") {
		t.Error("nil manager must never report warm")
	}
}

func TestWarmupLogsTelemetry(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprint(w, warmupOKBody())
	}))
	defer server.Close()

	var mu sync.Mutex
	var lines []string
	manager := NewWarmupManager(server.Client()).WithWarmupLogger(func(format string, args ...any) {
		mu.Lock()
		defer mu.Unlock()
		lines = append(lines, fmt.Sprintf(format, args...))
	})
	if err := manager.Warm(context.Background(), server.URL+"/act", ""); err != nil {
		t.Fatalf("Warm: %v", err)
	}
	mu.Lock()
	defer mu.Unlock()
	if len(lines) != 1 {
		t.Fatalf("log lines = %d, want 1: %v", len(lines), lines)
	}
	line := lines[0]
	for _, want := range []string{"policy warmup:", "ok=true", "checkpoint_sha=abc123", "latency_ms="} {
		if !strings.Contains(line, want) {
			t.Errorf("log line %q missing %q", line, want)
		}
	}
}
