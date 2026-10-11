package api

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/plasma/fh-mahjong/internal/bot"
	pb "github.com/plasma/fh-mahjong/proto"
)

func agentList(avail map[string]bool, ids ...string) func() []RLAgentInfo {
	return func() []RLAgentInfo {
		out := make([]RLAgentInfo, 0, len(ids))
		for _, id := range ids {
			out = append(out, RLAgentInfo{ID: id, Label: "AI " + id, Available: avail[id]})
		}
		return out
	}
}

// seatAgents creates a table hosted by user 101 (alice) and seats bots 1..3:
// "-" is a heuristic bot, any other value an RL bot with that RLAgent ("" =
// legacy seat with no agent id). Written straight into the seat array so a
// legacy empty RLAgent survives.
func seatAgents(t *testing.T, m *Matchmaker, tableID string, agents [3]string) {
	t.Helper()
	if _, err := m.CreatePrivateTable(tableID, 101, "alice"); err != nil {
		t.Fatalf("create: %v", err)
	}
	if _, err := m.MutatePrivateTable(tableID, func(pt *PrivateTable) error {
		for i, a := range agents {
			if a == "-" {
				pt.Seats[i+1] = SeatConfig{Kind: "bot", Difficulty: pb.Difficulty_DIFFICULTY_HEURISTIC}
			} else {
				pt.Seats[i+1] = SeatConfig{Kind: "bot", Difficulty: pb.Difficulty_DIFFICULTY_RL, RLAgent: a}
			}
		}
		return nil
	}); err != nil {
		t.Fatalf("configure seats: %v", err)
	}
}

func TestValidateSeatResolvesDefaultAndRejectsUnknownOrDown(t *testing.T) {
	m := &Matchmaker{RLAgents: agentList(map[string]bool{"v4": true, "v3": false}, "v4", "v3")}
	if id, err := m.ValidateSeat(pb.Difficulty_DIFFICULTY_RL, ""); err != nil || id != "v4" {
		t.Fatalf("empty agent: got %q, %v; want v4, nil", id, err)
	}
	if _, err := m.ValidateSeat(pb.Difficulty_DIFFICULTY_RL, "v9"); !errors.Is(err, errUnknownRLAgent) {
		t.Fatalf("unknown agent: err = %v, want errUnknownRLAgent", err)
	}
	if _, err := m.ValidateSeat(pb.Difficulty_DIFFICULTY_RL, "v3"); !errors.Is(err, errRLAgentUnavailable) {
		t.Fatalf("down agent: err = %v, want errRLAgentUnavailable", err)
	}
	if id, err := m.ValidateSeat(pb.Difficulty_DIFFICULTY_HEURISTIC, "v4"); err != nil || id != "" {
		t.Fatalf("heuristic seat: got %q, %v; want \"\", nil (agent ignored)", id, err)
	}
	if _, err := (&Matchmaker{}).ValidateSeat(pb.Difficulty_DIFFICULTY_RL, ""); !errors.Is(err, errRLAgentUnavailable) {
		t.Fatalf("no registry: err = %v, want errRLAgentUnavailable", err)
	}
}

func TestSeatProtoCarriesRLAgent(t *testing.T) {
	table := &PrivateTable{}
	if err := table.setSeat(2, "bot", pb.Difficulty_DIFFICULTY_RL, "v3"); err != nil {
		t.Fatal(err)
	}
	if err := table.setSeat(1, "bot", pb.Difficulty_DIFFICULTY_HEURISTIC, "v3"); err != nil {
		t.Fatal(err)
	}
	seats := table.toProto().GetSeats()
	if got := seats[2].GetRlAgent(); got != "v3" {
		t.Fatalf("RL seat rl_agent = %q, want v3", got)
	}
	if got := seats[1].GetRlAgent(); got != "" {
		t.Fatalf("heuristic seat rl_agent = %q, want empty", got)
	}
}

func TestConfigListsAgents(t *testing.T) {
	gin.SetMode(gin.TestMode)
	s := &Server{Matchmaker: &Matchmaker{RLAgents: agentList(map[string]bool{"v4": true}, "v4", "v3")}}
	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	s.handleConfig(c)
	var body struct {
		RLAgentAvailable bool          `json:"rlAgentAvailable"`
		RLAgents         []RLAgentInfo `json:"rlAgents"`
	}
	if err := json.Unmarshal(w.Body.Bytes(), &body); err != nil || w.Code != http.StatusOK {
		t.Fatalf("status %d, decode %v", w.Code, err)
	}
	if !body.RLAgentAvailable || len(body.RLAgents) != 2 || body.RLAgents[0].ID != "v4" || body.RLAgents[1].Available {
		t.Fatalf("config = %+v", body)
	}
	empty := httptest.NewRecorder()
	c2, _ := gin.CreateTestContext(empty)
	(&Server{Matchmaker: &Matchmaker{}}).handleConfig(c2)
	if got := empty.Body.String(); got != `{"rlAgentAvailable":false,"rlAgents":[]}` {
		t.Fatalf("no registry config = %s", got)
	}
}

func TestStartWarmsSeatedAgentsOnlyAndDefaultsLegacySeats(t *testing.T) {
	var warmed []string
	var resolved []string
	m := newWarmupTestMatchmaker()
	m.RLAgents = agentList(map[string]bool{"v4": true, "v3": true, "v2": true}, "v4", "v3", "v2")
	m.WarmRLEndpoints = func(_ context.Context, ids []string) error {
		warmed = append([]string(nil), ids...)
		return nil
	}
	m.SeatPolicyResolver = func(d pb.Difficulty, agentID, roomID string, seat uint32) (bot.Policy, error) {
		resolved = append(resolved, agentID)
		return bot.NewPolicy(pb.Difficulty_DIFFICULTY_HEURISTIC)
	}
	m.RLPolicyIdentity = func(agentID string) string { return "ckpt-" + agentID }
	seatAgents(t, m, "t-agents", [3]string{"v3", "", "v3"}) // "" = a seat configured before the deploy
	if _, err := m.StartPrivateTable("t-agents", 101); err != nil {
		t.Fatalf("start: %v", err)
	}
	if want := []string{"v3", "v4"}; len(warmed) != 2 || warmed[0] != want[0] || warmed[1] != want[1] {
		t.Fatalf("warmed %v, want %v (distinct, seat order, legacy seat → default)", warmed, want)
	}
	if want := []string{"v3", "v4", "v3"}; len(resolved) != 3 || resolved[0] != want[0] || resolved[1] != want[1] || resolved[2] != want[2] {
		t.Fatalf("resolved %v, want %v", resolved, want)
	}
}

func TestStartRefusesWhenSeatedAgentWentDown(t *testing.T) {
	m := newWarmupTestMatchmaker()
	m.RLAgents = agentList(map[string]bool{"v4": true}, "v4", "v3")
	m.WarmRLEndpoints = func(_ context.Context, ids []string) error {
		for _, id := range ids {
			if id == "v3" {
				return errors.New("v3 cold")
			}
		}
		return nil
	}
	seatAgents(t, m, "t-agent-down", [3]string{"v3", "-", "-"}) // "-" = heuristic seat
	if _, err := m.StartPrivateTable("t-agent-down", 101); !errors.Is(err, ErrRLWarmupFailed) {
		t.Fatalf("start err = %v, want ErrRLWarmupFailed", err)
	}
}

func TestBotDisplayNameUsesAgentLabel(t *testing.T) {
	if got := botDisplayName(1, pb.Difficulty_DIFFICULTY_RL, "AI v4"); got != "Bot 2 (AI v4)" {
		t.Fatalf("got %q", got)
	}
	if got := botDisplayName(1, pb.Difficulty_DIFFICULTY_RL, ""); got != "Bot 2 (RL)" {
		t.Fatalf("got %q", got)
	}
}
