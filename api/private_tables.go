package api

import (
	"errors"
	"fmt"
	"sync"

	pb "github.com/plasma/fh-mahjong/proto"
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
}

// newConfiguringTable returns a table with all four seats empty.
func newConfiguringTable(tableID string, hostUserID uint) *PrivateTable {
	return &PrivateTable{
		TableID:    tableID,
		HostUserID: hostUserID,
		State:      "configuring",
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
	return &pb.PrivateTableState{
		TableId:    t.TableID,
		HostUserId: uint32(t.HostUserID),
		Seats:      seats,
		State:      t.State,
		MatchId:    t.MatchID,
	}
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
