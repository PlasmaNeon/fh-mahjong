package bot

import (
	"log"
	"sort"
	"sync"
	"sync/atomic"
	"time"

	"github.com/plasma/fh-mahjong/internal/engine"
	pb "github.com/plasma/fh-mahjong/proto"
	"google.golang.org/protobuf/proto"
)

// shadowLatencyRingSize bounds the recent-latency sample kept for the P95
// estimate — a fixed-size ring rather than an unbounded log, so long-running
// shadow mode never grows memory with decision count.
const shadowLatencyRingSize = 256

// shadowStatsLogEvery controls how often (in shadow decisions) an aggregate
// stats line is logged, mirroring remote.HTTPPolicy's statsLogEvery default.
const shadowStatsLogEvery = 100

// ShadowMetrics is a point-in-time snapshot of ShadowPolicy's counters.
type ShadowMetrics struct {
	Decisions    uint64
	ShadowErrors uint64
	Dropped      uint64
	Agreements   uint64
	P95LatencyMs float64
}

// shadowJob is one mirrored decision queued for the worker goroutine. Both
// Ctx and PrimaryAction are deep clones taken at enqueue time — the worker
// runs asynchronously, well after the room may have mutated the live state
// or acted on the returned action, so the job must not alias anything the
// caller still owns.
type shadowJob struct {
	Ctx           *DecisionContext
	PrimaryAction *pb.PlayerAction
}

// ShadowPolicy wraps a primary Policy (the currently-deployed champion, which
// keeps actually driving the game) with a candidate ContextPolicy that
// silently mirrors each decision for comparison. The primary always answers
// synchronously and its action is what gets returned/played; the shadow's
// evaluation happens on a background worker and can never slow down or fail
// a live game.
//
// ShadowPolicy implements both Policy and ContextPolicy so it can be wired
// in wherever a plain bot.Policy is expected (legacy ChooseAction callers get
// the primary's answer with no mirroring — see ChooseAction) and wherever
// room dispatch prefers ContextPolicy (internal/api/room_bot.go), which is
// the shadow-mode use case this type exists for.
type ShadowPolicy struct {
	primary Policy
	shadow  ContextPolicy

	queue      chan shadowJob
	workerDone chan struct{}
	closeOnce  sync.Once

	decisions    atomic.Uint64
	shadowErrors atomic.Uint64
	dropped      atomic.Uint64
	agreements   atomic.Uint64

	latMu     sync.Mutex
	latencies []float64
	latNext   int
}

var _ Policy = (*ShadowPolicy)(nil)
var _ ContextPolicy = (*ShadowPolicy)(nil)

// NewShadowPolicy starts the background worker and returns a ShadowPolicy
// ready to serve decisions. queueSize bounds how many mirrored decisions may
// be in flight before new ones are dropped (Metrics().Dropped) rather than
// blocking the primary's answer; queueSize <= 0 is treated as 1.
func NewShadowPolicy(primary Policy, shadow ContextPolicy, queueSize int) *ShadowPolicy {
	if queueSize <= 0 {
		queueSize = 1
	}
	policy := &ShadowPolicy{
		primary:    primary,
		shadow:     shadow,
		queue:      make(chan shadowJob, queueSize),
		workerDone: make(chan struct{}),
	}
	go policy.run()
	return policy
}

// ChooseAction implements the legacy (state, seat) Policy interface. The
// legacy path carries no events and no stable decision index, so — per the
// package's ContextPolicy contract — there is nothing meaningful to mirror
// with; mirroring is intentionally skipped here rather than synthesized from
// a fake context. Shadow mode's actual use case (room dispatch, see
// internal/api/room_bot.go's ContextPolicy preference) always goes through
// ChooseActionCtx, so this is not a practical gap.
func (s *ShadowPolicy) ChooseAction(state *pb.GameState, seat uint32) *pb.PlayerAction {
	if s == nil || s.primary == nil {
		return nil
	}
	return s.primary.ChooseAction(state, seat)
}

// ChooseActionCtx answers synchronously from the primary — via its own
// ChooseActionCtx if it implements ContextPolicy, else via legacy
// ChooseAction — then enqueues a deep-cloned copy of the decision for the
// background worker to mirror against the shadow policy. Enqueueing never
// blocks: a full queue increments Dropped and the decision is skipped.
func (s *ShadowPolicy) ChooseActionCtx(ctx *DecisionContext) *pb.PlayerAction {
	if s == nil || ctx == nil {
		return nil
	}

	var action *pb.PlayerAction
	if ctxPolicy, ok := s.primary.(ContextPolicy); ok {
		action = ctxPolicy.ChooseActionCtx(ctx)
	} else if s.primary != nil {
		action = s.primary.ChooseAction(ctx.State, ctx.Seat)
	}

	s.enqueueShadow(ctx, action)

	return action
}

// enqueueShadow builds the deep-cloned job and performs the non-blocking
// send. proto.Clone on the state (and, if present, the primary's action)
// guards against the room mutating the live *pb.GameState — or acting on the
// returned *pb.PlayerAction — before the worker gets around to reading it;
// Events is a plain-value-struct slice, so a copy is already a full clone.
func (s *ShadowPolicy) enqueueShadow(ctx *DecisionContext, primaryAction *pb.PlayerAction) {
	if s == nil || s.shadow == nil || ctx.State == nil {
		return
	}

	clonedState, ok := proto.Clone(ctx.State).(*pb.GameState)
	if !ok || clonedState == nil {
		return
	}

	clonedEvents := make([]engine.PublicEvent, len(ctx.Events))
	copy(clonedEvents, ctx.Events)

	var clonedAction *pb.PlayerAction
	if primaryAction != nil {
		if cloned, ok := proto.Clone(primaryAction).(*pb.PlayerAction); ok {
			clonedAction = cloned
		}
	}

	job := shadowJob{
		Ctx: &DecisionContext{
			State:         clonedState,
			Seat:          ctx.Seat,
			DecisionIndex: ctx.DecisionIndex,
			Events:        clonedEvents,
		},
		PrimaryAction: clonedAction,
	}

	select {
	case s.queue <- job:
	default:
		s.dropped.Add(1)
	}
}

// run is the single worker goroutine: it drains the queue, calling the
// shadow policy on each cloned job, and exits once the queue is closed and
// drained (see Close).
func (s *ShadowPolicy) run() {
	defer close(s.workerDone)
	for job := range s.queue {
		s.evaluate(job)
	}
}

// evaluate calls the shadow policy for one job, recording latency, agreement
// (vs the primary's action, compared with proto.Equal), and errors. A panic
// inside the shadow policy is recovered and counted as a shadow error rather
// than taking down the worker goroutine (and therefore all future shadow
// mirroring) for the rest of the process.
func (s *ShadowPolicy) evaluate(job shadowJob) {
	start := time.Now()
	var shadowAction *pb.PlayerAction
	errored := false
	func() {
		defer func() {
			if r := recover(); r != nil {
				errored = true
				log.Printf("bot: shadow policy panic seat=%d decision_index=%d: %v", job.Ctx.Seat, job.Ctx.DecisionIndex, r)
			}
		}()
		shadowAction = s.shadow.ChooseActionCtx(job.Ctx)
	}()
	latencyMs := float64(time.Since(start)) / float64(time.Millisecond)

	if !errored && shadowAction == nil {
		errored = true
	}
	if errored {
		s.shadowErrors.Add(1)
	}

	agree := !errored && proto.Equal(job.PrimaryAction, shadowAction)
	if agree {
		s.agreements.Add(1)
	}

	s.recordLatency(latencyMs)
	count := s.decisions.Add(1)

	log.Printf(
		"bot: shadow decision seat=%d decision_index=%d latency_ms=%.2f agree=%v error=%v",
		job.Ctx.Seat, job.Ctx.DecisionIndex, latencyMs, agree, errored,
	)

	if count%shadowStatsLogEvery == 0 {
		metrics := s.Metrics()
		log.Printf(
			"bot: shadow stats decisions=%d errors=%d dropped=%d agreements=%d p95_latency_ms=%.2f",
			metrics.Decisions, metrics.ShadowErrors, metrics.Dropped, metrics.Agreements, metrics.P95LatencyMs,
		)
	}
}

func (s *ShadowPolicy) recordLatency(ms float64) {
	s.latMu.Lock()
	defer s.latMu.Unlock()
	if len(s.latencies) < shadowLatencyRingSize {
		s.latencies = append(s.latencies, ms)
		return
	}
	s.latencies[s.latNext] = ms
	s.latNext = (s.latNext + 1) % shadowLatencyRingSize
}

func (s *ShadowPolicy) p95LatencyMs() float64 {
	s.latMu.Lock()
	defer s.latMu.Unlock()
	n := len(s.latencies)
	if n == 0 {
		return 0
	}
	sorted := make([]float64, n)
	copy(sorted, s.latencies)
	sort.Float64s(sorted)
	idx := int(float64(n) * 0.95)
	if idx >= n {
		idx = n - 1
	}
	return sorted[idx]
}

// Metrics returns a snapshot of the shadow worker's counters, safe to call
// concurrently with live decisions.
func (s *ShadowPolicy) Metrics() ShadowMetrics {
	if s == nil {
		return ShadowMetrics{}
	}
	return ShadowMetrics{
		Decisions:    s.decisions.Load(),
		ShadowErrors: s.shadowErrors.Load(),
		Dropped:      s.dropped.Load(),
		Agreements:   s.agreements.Load(),
		P95LatencyMs: s.p95LatencyMs(),
	}
}

// Close closes the intake queue and waits for the worker to drain it and
// exit. Idempotent — safe to call more than once (or concurrently) via
// sync.Once guarding the channel close; every caller still blocks until the
// worker has actually finished.
func (s *ShadowPolicy) Close() {
	if s == nil {
		return
	}
	s.closeOnce.Do(func() {
		close(s.queue)
	})
	<-s.workerDone
}
