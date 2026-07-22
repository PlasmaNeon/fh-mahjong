package review

import (
	"context"
	"errors"
	"fmt"
	"sort"
	"time"

	"github.com/plasma/fh-mahjong/internal/engine"
	pb "github.com/plasma/fh-mahjong/proto"
)

// ErrUnreviewable wraps any failure reconstructing decisions from a paipu
// (see ExtractDecisions). Callers — notably the review HTTP API — map this
// to a 422, distinguishing "this paipu cannot be reviewed" from a transient
// policy-server failure.
var ErrUnreviewable = errors.New("unreviewable paipu")

// topGapCount is how many of a seat's largest chosen-vs-best probability
// gaps are surfaced in its SeatSummary.
const topGapCount = 5

// Report is the reviewer-facing critique of a completed match: the served
// policy's action distribution at every reviewable decision, plus per-seat
// rollups. Field names/types are a cross-task contract with the frontend —
// do not rename without updating Tasks 6/7.
type Report struct {
	SchemaVersion  int    `json:"schemaVersion"` // 1
	MatchID        string `json:"matchId"`
	Ruleset        string `json:"ruleset"`
	CheckpointPath string `json:"checkpointPath"`
	CheckpointStep int    `json:"checkpointStep"`
	// CheckpointSha256 is the content hash of the checkpoint that actually
	// produced every decision in this report (round 17, Finding 2) — unlike
	// CheckpointPath, it survives a same-path hot reload, so it's what a
	// STORED report should be keyed/compared on to tell "this cached report
	// still reflects the currently-serving bytes" apart from "the path
	// matches but the bytes changed underneath it". Empty when the serving
	// policy predates this field (legacy serve_policy.py), meaning
	// "unknown", not "no checkpoint".
	CheckpointSha256 string           `json:"checkpointSha256,omitempty"`
	GeneratedAt      time.Time        `json:"generatedAt"`
	Decisions        []ReportDecision `json:"decisions"`
	Seats            []SeatSummary    `json:"seats"` // exactly 4

	// ValuesCalibrated is false when the served checkpoint is a
	// privileged-critic model (adversarial round 15, Finding 4): serving
	// only ever feeds such a checkpoint's value head the public planes it
	// was NOT trained on, so every ReportDecision.Value in this report is
	// nil/absent rather than a number. Action ranking (Actions/ChosenProb/
	// TopGaps, all probability-based) is unaffected either way — a
	// privileged-critic checkpoint still yields a fully meaningful
	// action-ranking review, just not a value-based one.
	ValuesCalibrated bool `json:"valuesCalibrated"`
}

// ReportDecision is one reviewed decision: the policy's legal-action
// distribution at that point, and which action was actually chosen.
type ReportDecision struct {
	Seat        uint32  `json:"seat"`
	Round       int     `json:"round"`
	ActionIndex int     `json:"actionIndex"`
	ChosenID    int     `json:"chosenActionId"`
	ChosenProb  float32 `json:"chosenProb"`
	// Value is nil when the report's ValuesCalibrated is false (a
	// privileged-critic checkpoint served this decision) — see Report's doc.
	// Omitted from JSON entirely in that case, rather than published as a
	// misleading 0.0.
	Value   *float32     `json:"value,omitempty"`
	Actions []ActionProb `json:"actions"` // legal actions, sorted by prob desc
}

// ActionProb is one legal action's catalog id and probability.
type ActionProb struct {
	ActionID int     `json:"actionId"`
	Prob     float32 `json:"prob"`
}

// SeatSummary rolls up one seat's decisions across the match.
type SeatSummary struct {
	Seat           uint32   `json:"seat"`
	Decisions      int      `json:"decisions"`
	MeanChosenProb float32  `json:"meanChosenProb"`
	TopGaps        []GapRef `json:"topGaps"` // 5 largest prob gaps
}

// GapRef points at one decision's gap between the policy's top legal action
// and the action actually chosen.
type GapRef struct {
	Decision int     `json:"decision"` // index into Report.Decisions
	Gap      float32 `json:"gap"`      // top-action prob minus chosen-action prob
}

// BuildReport reconstructs every reviewable decision from paipu, evaluates
// them against client in chunked batches, and assembles the resulting
// Report. It never returns a partial report: any failure in decision
// reconstruction or policy evaluation aborts with an error and a nil report.
//
// eventWindow is forwarded to ExtractDecisions (see its doc); pass 0 unless
// the served policy has event_window > 0.
//
// ctx is forwarded to client.Evaluate (adversarial round 22, Finding 1): the
// caller decides whose lifetime governs the evaluation call — a shared
// build running via singleflight should be given a context detached from
// any single HTTP request, so one caller giving up doesn't cut off a build
// others are also waiting on.
func BuildReport(ctx context.Context, paipu *engine.Paipu, client PolicyClient, eventWindow uint32) (*Report, error) {
	decisions, err := ExtractDecisions(paipu, eventWindow)
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrUnreviewable, err)
	}

	observations := make([]*pb.SeatObservation, len(decisions))
	for i, d := range decisions {
		observations[i] = d.Observation
	}
	results, info, err := client.Evaluate(ctx, observations)
	if err != nil {
		return nil, fmt.Errorf("evaluate decisions: %w", err)
	}
	if len(results) != len(decisions) {
		return nil, fmt.Errorf("policy client returned %d results for %d decisions", len(results), len(decisions))
	}

	reportDecisions := make([]ReportDecision, len(decisions))
	for i, d := range decisions {
		rd, err := buildReportDecision(d, results[i])
		if err != nil {
			return nil, fmt.Errorf("decision %d: %w", i, err)
		}
		reportDecisions[i] = rd
	}

	report := &Report{
		SchemaVersion:    1,
		MatchID:          paipu.MatchID,
		Ruleset:          paipu.Ruleset,
		CheckpointPath:   info.Path,
		CheckpointStep:   info.Step,
		CheckpointSha256: info.Sha256,
		GeneratedAt:      time.Now().UTC(),
		Decisions:        reportDecisions,
		Seats:            buildSeatSummaries(reportDecisions),
		ValuesCalibrated: info.ValuesCalibrated,
	}
	return report, nil
}

// buildReportDecision converts one Decision + its policy result into a
// ReportDecision: filters Probs down to legal actions (per the
// observation's mask), sorts them by probability descending, and
// renormalizes over the legal subset. The server is expected to already
// mask illegal actions to zero probability mass, so renormalizing here is a
// no-op guard against a server that doesn't.
func buildReportDecision(d Decision, res PolicyResult) (ReportDecision, error) {
	mask := d.Observation.GetActionMask()
	if len(res.Probs) < len(mask) {
		return ReportDecision{}, fmt.Errorf("policy result has %d probs, mask has %d entries", len(res.Probs), len(mask))
	}

	actions := make([]ActionProb, 0, len(mask))
	var sumLegal float32
	for idx, m := range mask {
		if m == 0 {
			continue
		}
		p := res.Probs[idx]
		sumLegal += p
		actions = append(actions, ActionProb{ActionID: idx, Prob: p})
	}
	if len(actions) == 0 {
		return ReportDecision{}, fmt.Errorf("no legal actions in mask")
	}
	if sumLegal > 0 {
		for i := range actions {
			actions[i].Prob /= sumLegal
		}
	}
	sort.SliceStable(actions, func(i, j int) bool { return actions[i].Prob > actions[j].Prob })

	var chosenProb float32
	found := false
	for _, a := range actions {
		if a.ActionID == d.ChosenAction {
			chosenProb = a.Prob
			found = true
			break
		}
	}
	if !found {
		return ReportDecision{}, fmt.Errorf("chosen action %d is not legal per observation mask", d.ChosenAction)
	}

	return ReportDecision{
		Seat:        d.Seat,
		Round:       d.RoundIndex,
		ActionIndex: d.ActionIndex,
		ChosenID:    d.ChosenAction,
		ChosenProb:  chosenProb,
		Value:       res.Value,
		Actions:     actions,
	}, nil
}

// buildSeatSummaries and every other rollup below is prob-based (ChosenProb,
// TopGaps), never Value — so a nil Value (privileged-critic checkpoint,
// Report.ValuesCalibrated == false) affects nothing here: the review's
// action-ranking scoring is unaffected, only the per-decision Value display
// is absent.

// buildSeatSummaries computes the exactly-4 SeatSummary rollups from the
// already-built ReportDecisions.
func buildSeatSummaries(decisions []ReportDecision) []SeatSummary {
	summaries := make([]SeatSummary, 4)
	for seat := range summaries {
		summaries[seat].Seat = uint32(seat)
	}

	type gap struct {
		decisionIdx int
		gap         float32
	}
	gapsBySeat := make(map[uint32][]gap, 4)
	var sumProbBySeat [4]float32

	for i, d := range decisions {
		if d.Seat >= 4 {
			continue
		}
		summaries[d.Seat].Decisions++
		sumProbBySeat[d.Seat] += d.ChosenProb
		if len(d.Actions) > 0 {
			g := d.Actions[0].Prob - d.ChosenProb
			gapsBySeat[d.Seat] = append(gapsBySeat[d.Seat], gap{decisionIdx: i, gap: g})
		}
	}

	for seat := range summaries {
		if summaries[seat].Decisions > 0 {
			summaries[seat].MeanChosenProb = sumProbBySeat[seat] / float32(summaries[seat].Decisions)
		}
		seatGaps := gapsBySeat[uint32(seat)]
		sort.SliceStable(seatGaps, func(i, j int) bool { return seatGaps[i].gap > seatGaps[j].gap })
		n := topGapCount
		if len(seatGaps) < n {
			n = len(seatGaps)
		}
		topGaps := make([]GapRef, n)
		for i := 0; i < n; i++ {
			topGaps[i] = GapRef{Decision: seatGaps[i].decisionIdx, Gap: seatGaps[i].gap}
		}
		summaries[seat].TopGaps = topGaps
	}
	return summaries
}
