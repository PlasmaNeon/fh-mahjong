package api

import (
	"encoding/json"
	"strings"
	"testing"
	"time"

	"github.com/glebarez/sqlite"
	"github.com/plasma/fh-mahjong/internal/bot"
	"github.com/plasma/fh-mahjong/internal/engine"
	"github.com/plasma/fh-mahjong/internal/storage"
	pb "github.com/plasma/fh-mahjong/proto"
	"gorm.io/gorm"
)

func newPersistTestDB(t *testing.T) *gorm.DB {
	t.Helper()
	db, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	if err := storage.AutoMigrate(db); err != nil {
		t.Fatalf("automigrate: %v", err)
	}
	return db
}

func insertInProgressMatch(t *testing.T, db *gorm.DB, matchID string) {
	t.Helper()
	match := storage.Match{ID: matchID, Status: "in_progress", StartTime: time.Now(), Ruleset: "fenghua"}
	if err := db.Create(&match).Error; err != nil {
		t.Fatalf("insert match: %v", err)
	}
}

// GAP 3: a room persisted before natural MATCH_END must mark the match
// aborted while still writing the partial paipu.
func TestPersistMatch_AbortedBeforeMatchEnd(t *testing.T) {
	db := newPersistTestDB(t)
	insertInProgressMatch(t, db, "abort-match")

	room := NewRoom("abort-match", nil, db)
	room.registerPaipuPlayers()
	if err := room.Engine.Start(); err != nil {
		t.Fatalf("engine start: %v", err)
	}
	if room.Engine.State.Phase == pb.GamePhase_PHASE_MATCH_END {
		t.Fatal("test premise broken: match already ended")
	}

	room.persistMatch()

	var row storage.Match
	if err := db.First(&row, "id = ?", "abort-match").Error; err != nil {
		t.Fatalf("load match: %v", err)
	}
	if row.Status != "aborted" {
		t.Fatalf("status = %q, want aborted", row.Status)
	}
	if row.PaipuJSON == "" {
		t.Fatal("expected partial paipu to be persisted on abort")
	}
	if row.EndTime == nil {
		t.Fatal("expected EndTime to be set on abort")
	}
}

func TestPersistMatch_CompletedAtMatchEnd(t *testing.T) {
	db := newPersistTestDB(t)
	insertInProgressMatch(t, db, "complete-match")

	room := NewRoom("complete-match", nil, db)
	room.registerPaipuPlayers()
	if err := room.Engine.Start(); err != nil {
		t.Fatalf("engine start: %v", err)
	}
	room.Engine.State.Phase = pb.GamePhase_PHASE_MATCH_END

	room.persistMatch()

	var row storage.Match
	if err := db.First(&row, "id = ?", "complete-match").Error; err != nil {
		t.Fatalf("load match: %v", err)
	}
	if row.Status != "completed" {
		t.Fatalf("status = %q, want completed", row.Status)
	}
}

// End-to-end: a classic private game (single-hand cap) played to its natural
// end must persist as "completed" with a paipu, so it appears in the paipu
// library. Regression guard for the "classic never completed" bug.
func TestPersistMatch_ClassicSingleHandCompletes(t *testing.T) {
	db := newPersistTestDB(t)
	insertInProgressMatch(t, db, "classic-1hand-persist")

	room := NewRoom("classic-1hand-persist", nil, db, WithMatchOptions(engine.MatchOptions{
		Mode:          pb.MatchMode_MATCH_MODE_CLASSIC,
		ChongciConfig: classicSingleHandConfig(),
	}))
	room.registerPaipuPlayers()

	phase := runBotOnlyRoomUntilTerminal(t, room, 200_000)
	if phase != pb.GamePhase_PHASE_MATCH_END {
		t.Fatalf("phase = %v, want PHASE_MATCH_END (handNum=%d)", phase, room.Engine.State.HandNum)
	}

	room.persistMatch()

	var row storage.Match
	if err := db.First(&row, "id = ?", "classic-1hand-persist").Error; err != nil {
		t.Fatalf("load match: %v", err)
	}
	if row.Status != "completed" {
		t.Fatalf("status = %q, want completed (a played-out classic game must list)", row.Status)
	}
	if row.PaipuJSON == "" {
		t.Fatal("expected paipu to be persisted for a completed classic game")
	}
}

// GAP 3: a server drain (SIGTERM before redeploy) must persist every active
// room instead of orphaning in_progress rows with empty PaipuJSON.
func TestDrainActiveRooms_PersistsRunningRoom(t *testing.T) {
	db := newPersistTestDB(t)
	insertInProgressMatch(t, db, "drain-match")

	hub := NewHub()
	go hub.Run()
	m := NewMatchmaker(NewInMemoryQueue(), db, hub)

	room := NewRoom("drain-match", hub, db)
	// A connected human seat keeps the bots from playing the match to
	// completion on their own, so the room is mid-match when drained.
	room.Seats[0] = &Client{UserID: 7, Username: "human", Send: make(chan []byte, 64)}
	room.SeatOwners[0] = 7
	m.registerActiveRoom(room)

	go room.Start()

	m.DrainActiveRooms(5 * time.Second)

	var row storage.Match
	if err := db.First(&row, "id = ?", "drain-match").Error; err != nil {
		t.Fatalf("load match: %v", err)
	}
	if row.Status != "aborted" {
		t.Fatalf("status = %q, want aborted", row.Status)
	}
	if row.PaipuJSON == "" {
		t.Fatal("expected drained room to persist its partial paipu")
	}
}

// DrainActiveRooms must not hang on a room whose loop never ran.
func TestDrainActiveRooms_TimesOutOnStuckRoom(t *testing.T) {
	hub := NewHub()
	go hub.Run()
	m := NewMatchmaker(NewInMemoryQueue(), nil, hub)
	m.registerActiveRoom(NewRoom("stuck-match", hub, nil)) // Start never called

	done := make(chan struct{})
	go func() {
		m.DrainActiveRooms(200 * time.Millisecond)
		close(done)
	}()
	select {
	case <-done:
	case <-time.After(3 * time.Second):
		t.Fatal("DrainActiveRooms hung on a room that never started")
	}
}

// GAP 4: persistMatch must also write relational MatchPlayer rows so the
// dataset is SQL-queryable without parsing every paipu blob.
func TestPersistMatch_InsertsMatchPlayerRows(t *testing.T) {
	db := newPersistTestDB(t)
	insertInProgressMatch(t, db, "rows-match")

	room := NewRoom("rows-match", nil, db)
	room.SeatInfos = map[uint32]SeatInfo{
		0: {Kind: "human", Name: "Alice", UserID: 101},
		1: {Kind: "bot", Difficulty: pb.Difficulty_DIFFICULTY_HEURISTIC},
		2: {Kind: "bot", Difficulty: pb.Difficulty_DIFFICULTY_RL, PolicyID: "champ.pt@step9"},
		3: {Kind: "human", Name: "Bob", UserID: 102},
	}
	room.registerPaipuPlayers()
	if err := room.Engine.Start(); err != nil {
		t.Fatalf("engine start: %v", err)
	}
	room.Engine.State.Phase = pb.GamePhase_PHASE_MATCH_END
	room.Engine.State.Players[0].Score = 40
	room.Engine.State.Players[1].Score = -10
	room.Engine.State.Players[2].Score = 40
	room.Engine.State.Players[3].Score = -70

	room.persistMatch()

	var rows []storage.MatchPlayer
	if err := db.Where("match_id = ?", "rows-match").Order("seat asc").Find(&rows).Error; err != nil {
		t.Fatalf("load match players: %v", err)
	}
	if len(rows) != 4 {
		t.Fatalf("expected 4 MatchPlayer rows, got %d", len(rows))
	}

	if r := rows[0]; r.UserID != 101 || r.IsBot || r.FinalScore != 40 {
		t.Fatalf("seat 0 row wrong: %+v", r)
	}
	if r := rows[1]; !r.IsBot || r.Difficulty != "heuristic" || r.UserID != 0 {
		t.Fatalf("seat 1 row wrong: %+v", r)
	}
	if r := rows[2]; !r.IsBot || r.Difficulty != "rl" || r.PolicyID != "champ.pt@step9" {
		t.Fatalf("seat 2 row wrong: %+v", r)
	}
	// Placements: 40/40 tie for 1st, -10 is 3rd, -70 is 4th.
	wantPlacement := []uint{1, 3, 1, 4}
	for i, r := range rows {
		if r.Placement != wantPlacement[i] {
			t.Fatalf("seat %d placement = %d, want %d", i, r.Placement, wantPlacement[i])
		}
	}
}

// Persistence failures must be reported, not silently swallowed (a drained
// deploy would otherwise claim success while the match stayed in_progress).
func TestPersistMatch_ReportsDBFailure(t *testing.T) {
	db := newPersistTestDB(t)
	insertInProgressMatch(t, db, "failing-match")

	room := NewRoom("failing-match", nil, db)
	room.registerPaipuPlayers()
	if err := room.Engine.Start(); err != nil {
		t.Fatalf("engine start: %v", err)
	}
	if err := db.Migrator().DropTable("matches"); err != nil {
		t.Fatalf("drop table: %v", err)
	}

	if err := room.persistMatch(); err == nil {
		t.Fatal("expected persistMatch to report the failed write")
	}
}

// The Match update and MatchPlayer insert are one transaction: if the row
// insert fails nothing is committed, so a retry/backfill sees a consistent
// in_progress row instead of a half-persisted match.
func TestPersistMatch_TransactionalRows(t *testing.T) {
	db := newPersistTestDB(t)
	insertInProgressMatch(t, db, "tx-match")

	room := NewRoom("tx-match", nil, db)
	room.registerPaipuPlayers()
	if err := room.Engine.Start(); err != nil {
		t.Fatalf("engine start: %v", err)
	}
	if err := db.Migrator().DropTable("match_players"); err != nil {
		t.Fatalf("drop table: %v", err)
	}

	if err := room.persistMatch(); err == nil {
		t.Fatal("expected persistMatch to fail when MatchPlayer insert fails")
	}
	var row storage.Match
	if err := db.First(&row, "id = ?", "tx-match").Error; err != nil {
		t.Fatalf("load match: %v", err)
	}
	if row.Status != "in_progress" || row.PaipuJSON != "" {
		t.Fatalf("expected rollback to keep the match untouched, got status=%q paipuLen=%d", row.Status, len(row.PaipuJSON))
	}
}

// A drained room must persist the hand in progress, not just completed
// rounds: aborting during the first hand would otherwise store a paipu with
// zero rounds, silently losing every deal and action.
func TestDrainActiveRooms_KeepsInProgressHand(t *testing.T) {
	db := newPersistTestDB(t)
	insertInProgressMatch(t, db, "midhand-match")

	hub := NewHub()
	go hub.Run()
	m := NewMatchmaker(NewInMemoryQueue(), db, hub)

	room := NewRoom("midhand-match", hub, db)
	room.Seats[0] = &Client{UserID: 7, Username: "human", Send: make(chan []byte, 64)}
	room.SeatOwners[0] = 7
	m.registerActiveRoom(room)
	go room.Start()

	m.DrainActiveRooms(5 * time.Second)

	var row storage.Match
	if err := db.First(&row, "id = ?", "midhand-match").Error; err != nil {
		t.Fatalf("load match: %v", err)
	}
	var paipu engine.Paipu
	if err := json.Unmarshal([]byte(row.PaipuJSON), &paipu); err != nil {
		t.Fatalf("parse persisted paipu: %v", err)
	}
	if len(paipu.Rounds) == 0 {
		t.Fatal("aborted paipu lost the in-progress hand (zero rounds persisted)")
	}
	last := paipu.Rounds[len(paipu.Rounds)-1]
	if len(last.Deals[0]) == 0 {
		t.Fatal("in-progress hand persisted without deals")
	}
	if last.Result != nil {
		t.Fatalf("in-progress hand must persist with nil result, got %+v", last.Result)
	}
}

// The shutdown sequence must persist BEFORE unregistering the room: if
// SIGTERM lands between OnShutdown and the DB write, DrainActiveRooms would
// otherwise no longer see the room and the process could exit mid-write.
func TestRoomShutdown_PersistsBeforeOnShutdown(t *testing.T) {
	db := newPersistTestDB(t)
	insertInProgressMatch(t, db, "order-match")

	room := NewRoom("order-match", nil, db)
	room.Seats[0] = &Client{UserID: 7, Username: "human", Send: make(chan []byte, 64)}
	room.SeatOwners[0] = 7

	statusAtUnregister := make(chan string, 1)
	room.OnShutdown = func() {
		var row storage.Match
		if err := db.First(&row, "id = ?", "order-match").Error; err != nil {
			statusAtUnregister <- "load-error: " + err.Error()
			return
		}
		statusAtUnregister <- row.Status
	}

	go room.Start()
	room.Shutdown <- true
	<-room.Done

	if got := <-statusAtUnregister; got == "in_progress" {
		t.Fatal("room was unregistered while the match was still unpersisted (in_progress)")
	}
}

// observedIDsPolicy stubs an RL policy that reports which checkpoints
// actually served its actions.
type observedIDsPolicy struct {
	stubPolicy
	ids []string
}

func (p observedIDsPolicy) ObservedPolicyIDs() []string { return p.ids }

// A policy hot reload mid-match must not corrupt attribution: the persisted
// labels reflect the checkpoints that actually served actions, not just the
// identity captured at match start.
func TestPersistMatch_ReconcilesObservedPolicyIDs(t *testing.T) {
	db := newPersistTestDB(t)
	insertInProgressMatch(t, db, "observed-match")

	room := NewRoom("observed-match", nil, db)
	room.SeatInfos = map[uint32]SeatInfo{
		0: {Kind: "human", Name: "Alice", UserID: 101},
		1: {Kind: "bot", Difficulty: pb.Difficulty_DIFFICULTY_HEURISTIC},
		2: {Kind: "bot", Difficulty: pb.Difficulty_DIFFICULTY_RL, PolicyID: "a.pt@step100"},
		3: {Kind: "bot", Difficulty: pb.Difficulty_DIFFICULTY_RL, PolicyID: "a.pt@step100"},
	}
	// Seat 2's endpoint hot-reloaded mid-match; seat 3 reported nothing
	// (older server) and must keep its match-start label.
	room.SeatPolicies = map[uint32]bot.Policy{
		2: observedIDsPolicy{ids: []string{"a.pt@step100", "b.pt@step200"}},
		3: observedIDsPolicy{},
	}
	room.registerPaipuPlayers()
	if err := room.Engine.Start(); err != nil {
		t.Fatalf("engine start: %v", err)
	}
	room.Engine.State.Phase = pb.GamePhase_PHASE_MATCH_END

	if err := room.persistMatch(); err != nil {
		t.Fatalf("persistMatch: %v", err)
	}

	var row storage.Match
	if err := db.First(&row, "id = ?", "observed-match").Error; err != nil {
		t.Fatalf("load match: %v", err)
	}
	var paipu engine.Paipu
	if err := json.Unmarshal([]byte(row.PaipuJSON), &paipu); err != nil {
		t.Fatalf("parse paipu: %v", err)
	}
	if got := paipu.Players[2].PolicyID; got != "a.pt@step100,b.pt@step200" {
		t.Fatalf("seat 2 policyId = %q, want observed checkpoints joined", got)
	}
	if got := paipu.Players[3].PolicyID; got != "a.pt@step100" {
		t.Fatalf("seat 3 policyId = %q, want match-start label kept", got)
	}

	var mpRows []storage.MatchPlayer
	if err := db.Where("match_id = ? AND seat = 2", "observed-match").Find(&mpRows).Error; err != nil || len(mpRows) != 1 {
		t.Fatalf("load seat 2 row: %v (%d rows)", err, len(mpRows))
	}
	if mpRows[0].PolicyID != "a.pt@step100,b.pt@step200" {
		t.Fatalf("seat 2 MatchPlayer policyId = %q", mpRows[0].PolicyID)
	}
}

// The PolicyID column is varchar(512); an oversized label must be truncated
// rather than failing the insert and rolling back the whole match write.
func TestPersistMatch_TruncatesOversizedPolicyID(t *testing.T) {
	db := newPersistTestDB(t)
	insertInProgressMatch(t, db, "longid-match")

	room := NewRoom("longid-match", nil, db)
	longID := strings.Repeat("c", 600)
	room.SeatInfos = map[uint32]SeatInfo{
		2: {Kind: "bot", Difficulty: pb.Difficulty_DIFFICULTY_RL, PolicyID: longID},
	}
	room.registerPaipuPlayers()
	if err := room.Engine.Start(); err != nil {
		t.Fatalf("engine start: %v", err)
	}
	room.Engine.State.Phase = pb.GamePhase_PHASE_MATCH_END

	if err := room.persistMatch(); err != nil {
		t.Fatalf("persistMatch must survive oversized policy ids: %v", err)
	}
	var rows []storage.MatchPlayer
	if err := db.Where("match_id = ? AND seat = 2", "longid-match").Find(&rows).Error; err != nil || len(rows) != 1 {
		t.Fatalf("load seat 2 row: %v (%d rows)", err, len(rows))
	}
	if len(rows[0].PolicyID) > 512 {
		t.Fatalf("PolicyID not bounded: %d chars", len(rows[0].PolicyID))
	}
}

// Transient DB failures during shutdown are retried before giving up.
func TestRoomShutdown_RetriesTransientPersistFailure(t *testing.T) {
	db := newPersistTestDB(t)
	insertInProgressMatch(t, db, "retry-match")

	// Fail the first two write attempts, then recover.
	var failures int
	if err := db.Callback().Update().Before("gorm:update").Register("test:failtwice", func(tx *gorm.DB) {
		if failures < 2 {
			failures++
			tx.AddError(gorm.ErrInvalidTransaction)
		}
	}); err != nil {
		t.Fatalf("register callback: %v", err)
	}

	room := NewRoom("retry-match", nil, db)
	room.Seats[0] = &Client{UserID: 7, Username: "human", Send: make(chan []byte, 64)}
	room.SeatOwners[0] = 7
	go room.Start()
	room.Shutdown <- true
	<-room.Done

	var row storage.Match
	if err := db.First(&row, "id = ?", "retry-match").Error; err != nil {
		t.Fatalf("load match: %v", err)
	}
	if row.Status == "in_progress" {
		t.Fatalf("expected retries to persist the match, still in_progress after %d failures", failures)
	}
}

// While the server is draining, no new match may start (it would be invisible
// to the in-flight drain and instantly orphaned by os.Exit).
func TestStartPrivateTable_RefusedWhileDraining(t *testing.T) {
	hub := NewHub()
	go hub.Run()
	m := NewMatchmaker(NewInMemoryQueue(), nil, hub)

	if _, err := m.CreatePrivateTable("t-drain", 101, "alice"); err != nil {
		t.Fatalf("join: %v", err)
	}
	if _, err := m.MutatePrivateTable("t-drain", func(pt *PrivateTable) error {
		for _, seat := range []uint32{1, 2, 3} {
			if err := pt.setSeat(seat, "bot", pb.Difficulty_DIFFICULTY_HEURISTIC); err != nil {
				return err
			}
		}
		return nil
	}); err != nil {
		t.Fatalf("configure: %v", err)
	}

	m.DrainActiveRooms(100 * time.Millisecond) // no rooms; flips draining mode

	if _, err := m.StartPrivateTable("t-drain", 101); err == nil {
		t.Fatal("expected StartPrivateTable to be refused while draining")
	}
}

// statsPolicy stubs an RL policy reporting decision provenance counts.
type statsPolicy struct {
	stubPolicy
	remote, fallback uint64
}

func (p statsPolicy) DecisionCounts() (uint64, uint64) { return p.remote, p.fallback }

// Seats whose endpoint fell back to the heuristic mid-match must be
// distinguishable: remote/fallback decision counts are persisted per seat.
func TestPersistMatch_RecordsDecisionProvenance(t *testing.T) {
	db := newPersistTestDB(t)
	insertInProgressMatch(t, db, "prov-match")

	room := NewRoom("prov-match", nil, db)
	room.SeatInfos = map[uint32]SeatInfo{
		2: {Kind: "bot", Difficulty: pb.Difficulty_DIFFICULTY_RL, PolicyID: "a.pt@step1"},
	}
	room.SeatPolicies = map[uint32]bot.Policy{
		2: statsPolicy{remote: 40, fallback: 3},
	}
	room.registerPaipuPlayers()
	if err := room.Engine.Start(); err != nil {
		t.Fatalf("engine start: %v", err)
	}
	room.Engine.State.Phase = pb.GamePhase_PHASE_MATCH_END

	if err := room.persistMatch(); err != nil {
		t.Fatalf("persistMatch: %v", err)
	}

	var row storage.Match
	if err := db.First(&row, "id = ?", "prov-match").Error; err != nil {
		t.Fatalf("load match: %v", err)
	}
	var paipu engine.Paipu
	if err := json.Unmarshal([]byte(row.PaipuJSON), &paipu); err != nil {
		t.Fatalf("parse paipu: %v", err)
	}
	if p := paipu.Players[2]; p.RemoteDecisions != 40 || p.FallbackDecisions != 3 {
		t.Fatalf("paipu provenance = (%d, %d), want (40, 3)", p.RemoteDecisions, p.FallbackDecisions)
	}

	var mp storage.MatchPlayer
	if err := db.Where("match_id = ? AND seat = 2", "prov-match").First(&mp).Error; err != nil {
		t.Fatalf("load row: %v", err)
	}
	if mp.RemoteDecisions != 40 || mp.FallbackDecisions != 3 {
		t.Fatalf("row provenance = (%d, %d), want (40, 3)", mp.RemoteDecisions, mp.FallbackDecisions)
	}
}

// Retried persistence must be idempotent: a retry after an ambiguous commit
// cannot duplicate seat rows.
func TestPersistMatch_IdempotentSeatRows(t *testing.T) {
	db := newPersistTestDB(t)
	insertInProgressMatch(t, db, "idem-match")

	room := NewRoom("idem-match", nil, db)
	room.registerPaipuPlayers()
	if err := room.Engine.Start(); err != nil {
		t.Fatalf("engine start: %v", err)
	}
	room.Engine.State.Phase = pb.GamePhase_PHASE_MATCH_END

	if err := room.persistMatch(); err != nil {
		t.Fatalf("first persist: %v", err)
	}
	if err := room.persistMatch(); err != nil {
		t.Fatalf("second persist (retry): %v", err)
	}

	var count int64
	if err := db.Model(&storage.MatchPlayer{}).Where("match_id = ?", "idem-match").Count(&count).Error; err != nil {
		t.Fatalf("count rows: %v", err)
	}
	if count != 4 {
		t.Fatalf("expected exactly 4 seat rows after a retried persist, got %d", count)
	}
}

// The draining gate must be atomic with room registration: a start that
// slips past an early check while the drain completes must still be refused
// at registration time and must not leave an orphaned in_progress row.
func TestStartPrivateTable_DrainGateLeavesNoOrphanRow(t *testing.T) {
	db := newPersistTestDB(t)
	hub := NewHub()
	go hub.Run()
	m := NewMatchmaker(NewInMemoryQueue(), db, hub)

	if _, err := m.CreatePrivateTable("t-race", 101, "alice"); err != nil {
		t.Fatalf("join: %v", err)
	}
	if _, err := m.MutatePrivateTable("t-race", func(pt *PrivateTable) error {
		for _, seat := range []uint32{1, 2, 3} {
			if err := pt.setSeat(seat, "bot", pb.Difficulty_DIFFICULTY_HEURISTIC); err != nil {
				return err
			}
		}
		return nil
	}); err != nil {
		t.Fatalf("configure: %v", err)
	}

	m.DrainActiveRooms(100 * time.Millisecond) // flips draining mode

	if _, err := m.StartPrivateTable("t-race", 101); err == nil {
		t.Fatal("expected StartPrivateTable to be refused while draining")
	}
	var count int64
	if err := db.Model(&storage.Match{}).Where("status = ?", "in_progress").Count(&count).Error; err != nil {
		t.Fatalf("count rows: %v", err)
	}
	if count != 0 {
		t.Fatalf("draining start orphaned %d in_progress match row(s)", count)
	}
	if _, active := m.GetActivePrivateTable("t-race"); active {
		t.Fatal("refused start must not leave the table registered as active")
	}
}

// A human seat played by a bot (never connected / disconnected takeover) must
// carry an automated-decision marker: datasets filtered as "human play" must
// be able to exclude bot-generated actions.
func TestPersistMatch_MarksAutomatedTakeoverOfHumanSeat(t *testing.T) {
	db := newPersistTestDB(t)
	insertInProgressMatch(t, db, "takeover-match")

	room := NewRoom("takeover-match", nil, db)
	room.SeatInfos = map[uint32]SeatInfo{
		0: {Kind: "human", Name: "Ghost", UserID: 101}, // reserved, never connects
	}
	room.SeatOwners[0] = 101
	room.registerPaipuPlayers()
	if err := room.Engine.Start(); err != nil {
		t.Fatalf("engine start: %v", err)
	}
	// Bots (including the takeover of seat 0) play some turns.
	room.advanceAutomatedSeatsN(8)
	room.Engine.State.Phase = pb.GamePhase_PHASE_MATCH_END

	if err := room.persistMatch(); err != nil {
		t.Fatalf("persistMatch: %v", err)
	}

	var row storage.Match
	if err := db.First(&row, "id = ?", "takeover-match").Error; err != nil {
		t.Fatalf("load match: %v", err)
	}
	var paipu engine.Paipu
	if err := json.Unmarshal([]byte(row.PaipuJSON), &paipu); err != nil {
		t.Fatalf("parse paipu: %v", err)
	}
	if paipu.Players[0].Kind != "human" {
		t.Fatalf("seat 0 must stay attributed to its human owner: %+v", paipu.Players[0])
	}
	if paipu.Players[0].AutomatedDecisions == 0 {
		t.Fatal("bot-takeover decisions on a human seat must be marked (automatedDecisions > 0)")
	}
	var mp storage.MatchPlayer
	if err := db.Where("match_id = ? AND seat = 0", "takeover-match").First(&mp).Error; err != nil {
		t.Fatalf("load row: %v", err)
	}
	if mp.AutomatedDecisions == 0 {
		t.Fatal("MatchPlayer row must mirror the automated-decision marker")
	}
}
