package api

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"sync"

	"github.com/gin-gonic/gin"
	"github.com/plasma/fh-mahjong/bot"
	pb "github.com/plasma/fh-mahjong/proto"
	"google.golang.org/protobuf/encoding/protojson"
)

// SeatConfig mirrors pb.SeatConfig for in-memory mutation. JSON marshalling
// uses field names that match the proto, so the WebSocket lobby_update
// payload is interchangeable between Go and TypeScript.
type SeatConfig struct {
	Kind       string        `json:"kind"`                 // "empty" | "human" | "bot"
	UserID     uint          `json:"userId,omitempty"`     // human
	Username   string        `json:"username,omitempty"`   // human
	Difficulty pb.Difficulty `json:"difficulty,omitempty"` // bot
}

// PrivateTable holds the configuration of a /table/:tableId waiting room
// before the actual match Room is constructed.
type PrivateTable struct {
	mu sync.Mutex

	TableID    string
	HostUserID uint
	Seats      [4]SeatConfig
	State      string // "configuring" | "started"
	MatchID    string // populated when State == "started"

	// MatchMode selects the match ruleset. The public constructor
	// newConfiguringTable sets this to MATCH_MODE_CLASSIC; direct struct
	// literal callers will see the zero value (MATCH_MODE_UNSPECIFIED).
	MatchMode pb.MatchMode
	// ChongciConfig is non-nil iff MatchMode == MATCH_MODE_CHONGCI.
	ChongciConfig *pb.ChongciConfig
}

// newConfiguringTable returns a table with all four seats empty and the
// default match mode (classic).
func newConfiguringTable(tableID string, hostUserID uint) *PrivateTable {
	return &PrivateTable{
		TableID:    tableID,
		HostUserID: hostUserID,
		State:      "configuring",
		MatchMode:  pb.MatchMode_MATCH_MODE_CLASSIC,
	}
}

// claimNextHumanSeat assigns the user to the lowest empty seat. Returns the
// seat index. Returns an error if the user is already seated or no empty
// human-allowed seat exists.
func (t *PrivateTable) claimNextHumanSeat(userID uint, username string) (uint32, error) {
	for i, s := range t.Seats {
		if s.Kind == "human" && s.UserID == userID {
			return uint32(i), nil // idempotent
		}
	}
	for i, s := range t.Seats {
		if s.Kind == "" || s.Kind == "empty" {
			t.Seats[i] = SeatConfig{
				Kind:     "human",
				UserID:   userID,
				Username: username,
			}
			return uint32(i), nil
		}
	}
	return 0, errors.New("no empty seat available")
}

// setSeat applies a host seat-config change. The target seat must not be
// held by a human (you can only mutate empty or bot seats).
func (t *PrivateTable) setSeat(seat uint32, kind string, difficulty pb.Difficulty) error {
	if seat > 3 {
		return fmt.Errorf("seat %d out of range", seat)
	}
	current := t.Seats[seat]
	if current.Kind == "human" {
		return errors.New("cannot overwrite a human-held seat")
	}
	switch kind {
	case "empty":
		t.Seats[seat] = SeatConfig{Kind: "empty"}
	case "bot":
		t.Seats[seat] = SeatConfig{Kind: "bot", Difficulty: difficulty}
	default:
		return fmt.Errorf("unsupported seat kind %q", kind)
	}
	return nil
}

// canStart returns nil if all four seats are non-empty.
func (t *PrivateTable) canStart() error {
	for i, s := range t.Seats {
		if s.Kind == "" || s.Kind == "empty" {
			return fmt.Errorf("seat %d is empty", i)
		}
	}
	return nil
}

// normalize fills any zero-value seats with the explicit "empty" kind so
// every serialized payload has four well-formed entries.
func (t *PrivateTable) normalize() {
	for i, s := range t.Seats {
		if s.Kind == "" {
			t.Seats[i] = SeatConfig{Kind: "empty"}
		}
	}
}

// toProto converts the in-memory table to a wire-ready proto message.
// Caller must hold t.mu.
func (t *PrivateTable) toProto() *pb.PrivateTableState {
	t.normalize()
	seats := make([]*pb.SeatConfig, 4)
	for i, s := range t.Seats {
		sc := &pb.SeatConfig{Kind: s.Kind}
		switch s.Kind {
		case "human":
			sc.UserId = uint32(s.UserID)
			sc.Username = s.Username
		case "bot":
			sc.Difficulty = s.Difficulty
		}
		seats[i] = sc
	}
	state := &pb.PrivateTableState{
		TableId:    t.TableID,
		HostUserId: uint32(t.HostUserID),
		Seats:      seats,
		State:      t.State,
		MatchId:    t.MatchID,
		MatchMode:  t.MatchMode,
	}
	if t.ChongciConfig != nil {
		cfg := *t.ChongciConfig
		state.ChongciConfig = &cfg
	}
	return state
}

// SnapshotProto returns a proto state snapshot, acquiring t.mu for the
// duration of the read. Use this from any caller that does NOT already
// hold the lock (e.g. the broadcast helper running after a mutation
// handler released the lock via defer).
func (t *PrivateTable) SnapshotProto() *pb.PrivateTableState {
	t.mu.Lock()
	defer t.mu.Unlock()
	return t.toProto()
}

// broadcastPrivateTable serializes the table to the proto JSON shape and
// fans it out via Hub.LobbyBroadcast. The frontend listens for
// `type: "lobby_update"` JSON messages and updates its seat state.
//
// Uses SnapshotProto so the marshal happens under the table lock; any
// caller that already holds the lock should release it before calling
// this helper (the registry methods return after `defer Unlock`, so the
// typical handler flow is safe).
func (s *Server) broadcastPrivateTable(table *PrivateTable) {
	if s.Hub == nil {
		return
	}
	statePB := table.SnapshotProto()
	stateJSON, err := protojson.MarshalOptions{EmitUnpopulated: true, UseEnumNumbers: true}.Marshal(statePB)
	if err != nil {
		return
	}
	envelope := struct {
		Type  string          `json:"type"`
		Table string          `json:"table"`
		State json.RawMessage `json:"state"`
	}{
		Type:  "lobby_update",
		Table: table.TableID,
		State: stateJSON,
	}
	payload, err := json.Marshal(envelope)
	if err != nil {
		return
	}
	go func() { s.Hub.LobbyBroadcast <- payload }()
}

func (s *Server) handlePrivateTableJoin(c *gin.Context) {
	userID, _ := c.Get("userID")
	username, _ := c.Get("username")
	tableID := c.Param("tableId")
	if tableID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "tableId is required"})
		return
	}

	if s.Matchmaker == nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{"error": "Private matchmaking unavailable"})
		return
	}

	if activeTable, isActive, isParticipant := s.Matchmaker.IsPrivateTableParticipant(tableID, userID.(uint)); isActive {
		if isParticipant {
			c.JSON(http.StatusOK, gin.H{"status": "active", "table": tableID, "matchId": activeTable.MatchID})
			return
		}
		c.JSON(http.StatusConflict, gin.H{"error": "This private table is already in an active game", "status": "active", "table": tableID, "matchId": activeTable.MatchID})
		return
	}

	table, err := s.Matchmaker.JoinOrCreatePrivateTable(tableID, userID.(uint), username.(string))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	s.broadcastPrivateTable(table)
	c.Data(http.StatusOK, "application/json", marshalPrivateTableJSON(table))
}

func (s *Server) handlePrivateTableGet(c *gin.Context) {
	tableID := c.Param("tableId")
	if s.Matchmaker == nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{"error": "Private matchmaking unavailable"})
		return
	}
	table := s.Matchmaker.GetConfiguringPrivateTable(tableID)
	if table == nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "table not found"})
		return
	}
	c.Data(http.StatusOK, "application/json", marshalPrivateTableJSON(table))
}

func (s *Server) handlePrivateTableSeat(c *gin.Context) {
	userID, _ := c.Get("userID")
	tableID := c.Param("tableId")

	if s.Matchmaker == nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{"error": "Private matchmaking unavailable"})
		return
	}

	var req struct {
		Seat       uint32        `json:"seat"`
		Kind       string        `json:"kind"`
		Difficulty pb.Difficulty `json:"difficulty"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	table, err := s.Matchmaker.MutatePrivateTable(tableID, func(t *PrivateTable) error {
		if t.HostUserID != userID.(uint) {
			return errHostOnly
		}
		if t.State != "configuring" {
			return ErrPrivateTableAlreadyStarted
		}
		if req.Kind == "bot" {
			if _, perr := bot.NewPolicy(req.Difficulty); perr != nil {
				return perr
			}
		}
		return t.setSeat(req.Seat, req.Kind, req.Difficulty)
	})
	if err != nil {
		status := http.StatusBadRequest
		switch {
		case errors.Is(err, errHostOnly):
			status = http.StatusForbidden
		case errors.Is(err, ErrPrivateTableAlreadyStarted):
			status = http.StatusConflict
		}
		c.JSON(status, gin.H{"error": err.Error()})
		return
	}

	s.broadcastPrivateTable(table)
	c.Data(http.StatusOK, "application/json", marshalPrivateTableJSON(table))
}

func (s *Server) handlePrivateTableStart(c *gin.Context) {
	userID, _ := c.Get("userID")
	tableID := c.Param("tableId")

	if s.Matchmaker == nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{"error": "Private matchmaking unavailable"})
		return
	}

	table, err := s.Matchmaker.StartPrivateTable(tableID, userID.(uint))
	if err != nil {
		status := http.StatusBadRequest
		switch {
		case errors.Is(err, ErrPrivateTableHostOnly):
			status = http.StatusForbidden
		case errors.Is(err, ErrPrivateTableNotFound):
			status = http.StatusNotFound
		case errors.Is(err, ErrPrivateTableAlreadyStarted):
			status = http.StatusConflict
		case errors.Is(err, ErrPrivateTablePersistFailed):
			status = http.StatusInternalServerError
		}
		c.JSON(status, gin.H{"error": err.Error()})
		return
	}

	s.broadcastPrivateTable(table)
	c.Data(http.StatusOK, "application/json", marshalPrivateTableJSON(table))
}

var errHostOnly = errors.New("only the host can modify seats")

// marshalPrivateTableJSON snapshots the table under its lock and returns
// the proto-JSON encoding. Safe to call from any handler regardless of
// whether the caller currently holds the lock — the registry mutate
// helpers release the lock before returning, so this path never blocks
// indefinitely.
func marshalPrivateTableJSON(t *PrivateTable) []byte {
	data, err := protojson.MarshalOptions{EmitUnpopulated: true, UseEnumNumbers: true}.Marshal(t.SnapshotProto())
	if err != nil {
		return []byte(`{"error":"failed to marshal table state"}`)
	}
	return data
}
