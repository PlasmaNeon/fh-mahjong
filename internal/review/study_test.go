package review

import (
	"context"
	"encoding/json"
	"errors"
	"math"
	"os"
	"reflect"
	"testing"
	"time"

	"github.com/plasma/fh-mahjong/internal/engine"
	"github.com/plasma/fh-mahjong/internal/review/reviewtest"
	"github.com/plasma/fh-mahjong/internal/rl"
	pb "github.com/plasma/fh-mahjong/proto"
	"google.golang.org/protobuf/proto"
)

func TestRolloutBranchesRetainTheReviewedPolicyContext(t *testing.T) {
	p := generateHeuristicPaipuV2(t, 7, engine.MatchOptions{})
	ds, err := extractDecisions(p, 0, true)
	if err != nil {
		t.Fatal(err)
	}
	for _, d := range ds {
		obs, err := rl.EncodeObservationWithEvents(d.Branch.State, d.Seat, d.DecisionIndex, d.Branch.PublicEvents(), 0)
		if err != nil {
			t.Fatal(err)
		}
		if !proto.Equal(obs, d.Observation) {
			t.Fatalf("decision %d branch changed the reviewed match context", d.DecisionIndex)
		}
	}
	// A legacy missing wind retains the engine's original East-round default.
	p.Rounds[0].PrevailingWind = 0
	if _, err := extractDecisions(p, 0, true); err != nil {
		t.Fatalf("legacy wind fallback: %v", err)
	}
}

func TestStudyEstimatesIgnoreRecordedOpponentHands(t *testing.T) {
	p := generateHeuristicPaipuV2(t, 7, engine.MatchOptions{})
	ds, err := extractDecisions(p, 0, true)
	if err != nil {
		t.Fatal(err)
	}
	d := ds[1]
	other := d
	other.Branch = d.Branch.CloneForBranch()
	if err := other.Branch.RedealUnseenForReview(d.Seat, 999); err != nil {
		t.Fatal(err)
	}
	a, err := assessRisk(context.Background(), d, 8, 777)
	if err != nil {
		t.Fatal(err)
	}
	b, err := assessRisk(context.Background(), other, 8, 777)
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(a, b) || !reflect.DeepEqual(assessDraw(d, p), assessDraw(other, p)) {
		t.Fatal("public estimates depend on recorded private allocation")
	}
}

func TestAdvancedReconstructionRejectsSettlementMismatchAndCancellation(t *testing.T) {
	p := generateHeuristicPaipuV2(t, 7, engine.MatchOptions{})
	p.Rounds[0].Result.ScoreChanges[0]++
	if _, err := extractDecisions(p, 0, true); err == nil {
		t.Fatal("tampered recorded payout accepted")
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, err := extractDecisionsContext(ctx, p, 0, true); !errors.Is(err, context.Canceled) {
		t.Fatalf("cancelled reconstruction continued: %v", err)
	}
}

func TestDrawOpportunityRecognizesAnActualLegalTsumo(t *testing.T) {
	for seed := uint64(0); seed < 32; seed++ {
		p := generateHeuristicPaipuV2(t, seed, engine.MatchOptions{})
		if p.Rounds[0].Result.WinType != "tsumo" {
			continue
		}
		ds, err := extractDecisions(p, 0, true)
		if err != nil {
			t.Fatal(err)
		}
		for _, d := range ds {
			if d.ChosenAction != rl.ActionTsumo {
				continue
			}
			opportunity := assessDraw(d, p)
			if opportunity == nil || !opportunity.Hit || opportunity.Chance <= 0 || opportunity.Chance > 1 || len(opportunity.Waits) == 0 {
				t.Fatalf("legal tsumo missing from public draw opportunity: %+v", opportunity)
			}
			copies := 0
			for _, wait := range opportunity.Waits {
				copies += wait.Remaining
			}
			if math.Abs(opportunity.Chance-float64(copies)/float64(opportunity.Unseen)) > 1e-12 {
				t.Fatal("draw chance is not weighted by public unseen copies")
			}
			return
		}
	}
	t.Fatal("deterministic fixture search did not find a tsumo")
}

func TestStudyRolloutsEvaluateEveryLegalCandidate(t *testing.T) {
	p := generateHeuristicPaipuV2(t, 7, engine.MatchOptions{})
	ds, err := extractDecisions(p, 0, true)
	if err != nil {
		t.Fatal(err)
	}
	stub, _ := reviewtest.NewEvaluateStub(t, reviewtest.Options{Sha: func() string { return "study-sha" }})
	client := NewHTTPPolicyClient(stub.URL, 0)
	// A late genuine decision still includes alternatives; each alternative
	// must be simulated to a scored terminal state, including pass/non-win.
	d := ds[len(ds)-1]
	results, _, err := client.Evaluate(context.Background(), []*pb.SeatObservation{d.Observation})
	if err != nil {
		t.Fatal(err)
	}
	rd, err := buildReportDecision(d, results[0])
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	cfg := DefaultStudyConfig()
	cfg.Worlds = 2
	cfg.RiskWorlds = 2
	values, err := evaluateActions(ctx, d, rd.Actions, client, 0, cfg, 19, "study-sha")
	if err != nil {
		t.Fatal(err)
	}
	if len(values) != len(rd.Actions) {
		t.Fatal("missing candidates")
	}
	for _, v := range values {
		if v.Samples != 2 || math.IsNaN(v.Mean) || math.IsInf(v.Mean, 0) {
			t.Fatalf("invalid result %+v", v)
		}
	}
}

func TestStudyResumeAndCheckpointIdentity(t *testing.T) {
	p := generateHeuristicPaipuV2(t, 17, engine.MatchOptions{})
	stub, ctl := reviewtest.NewEvaluateStub(t, reviewtest.Options{Sha: func() string { return "study-sha" }})
	cfg := DefaultStudyConfig()
	cfg.Worlds = 1
	cfg.RiskWorlds = 1
	stop := errors.New("stop after durable risk")
	var partial *Report
	save := func(r *Report, phase string, done, total int) error {
		b, _ := json.Marshal(r)
		if err := json.Unmarshal(b, &partial); err != nil {
			t.Fatal(err)
		}
		if phase == "risk" {
			return stop
		}
		return nil
	}
	_, err := BuildStudy(context.Background(), p, NewHTTPPolicyClient(stub.URL, 0), 0, cfg, "study-sha", nil, save)
	if !errors.Is(err, stop) || partial == nil || partial.Study.Complete || partial.Decisions[0].Risk == nil {
		t.Fatalf("partial checkpoint invalid: %v", err)
	}
	calls := ctl.EvalCount()
	_, err = BuildStudy(context.Background(), p, NewHTTPPolicyClient(stub.URL, 0), 0, cfg, "study-sha", partial, func(r *Report, phase string, done, total int) error { return stop })
	if !errors.Is(err, stop) || ctl.EvalCount() != calls {
		t.Fatal("resume repeated completed policy work")
	}
	_, err = BuildStudy(context.Background(), p, NewHTTPPolicyClient(stub.URL, 0), 0, cfg, "different-sha", partial, nil)
	if err == nil {
		t.Fatal("mixed checkpoint accepted")
	}
}

// Opt-in genuine checkpoint smoke; normal CI uses deterministic policy stubs.
func TestStudyRealCheckpoint(t *testing.T) {
	url := os.Getenv("FH_REVIEW_SMOKE_URL")
	if url == "" {
		t.Skip("opt-in real checkpoint")
	}
	p := generateHeuristicPaipuV2(t, 7, engine.MatchOptions{})
	b, _ := json.Marshal(p)
	if err := os.WriteFile("/tmp/fh-review-native.json", b, 0600); err != nil {
		t.Fatal(err)
	}
	client := NewHTTPPolicyClientWithToken(url, 0, "local-replay-validation")
	sha, err := client.CurrentCheckpointSha256(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	cfg := DefaultStudyConfig()
	cfg.Worlds = 2
	cfg.RiskWorlds = 128
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Minute)
	defer cancel()
	report, err := BuildStudy(ctx, p, client, 0, cfg, sha, nil, func(r *Report, phase string, done, total int) error {
		b, e := json.Marshal(r)
		if e != nil {
			return e
		}
		if e = os.WriteFile("/tmp/fh-review-real-report.json", b, 0600); e != nil {
			return e
		}
		t.Logf("%s %d/%d", phase, done, total)
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	if !report.Study.Complete {
		t.Fatal("incomplete")
	}
}
