package engine

import pb "github.com/plasma/fh-mahjong/proto"

// --- Paipu JSON Types ---

type PaipuTile struct {
	ID    uint32  `json:"id"`
	Suit  pb.Suit `json:"suit"`
	Value uint32  `json:"value"`
}

type PaipuPlayer struct {
	Seat   uint32 `json:"seat"`
	Name   string `json:"name"`
	UserID uint   `json:"userId"`
	// Seat-composition labels for dataset use. Empty in paipu recorded
	// before they existed (readers must treat absence as unknown).
	Kind       string `json:"kind,omitempty"`       // "human" | "bot"
	Difficulty string `json:"difficulty,omitempty"` // bots: "heuristic" | "rl"
	// PolicyID is the RL serving checkpoint identity: the match-start label
	// (from /healthz), reconciled at persist time to the comma-joined
	// checkpoints that actually served the seat's actions. If
	// RemoteDecisions is 0 the label is the configured endpoint identity,
	// not evidence the model ever acted.
	PolicyID string `json:"policyId,omitempty"`
	// Decision provenance for RL seats: how many decisions the remote model
	// served vs how many fell back to the local heuristic (per-decision
	// degradation). A pure-RL dataset filter is fallbackDecisions == 0.
	RemoteDecisions   uint64 `json:"remoteDecisions,omitempty"`
	FallbackDecisions uint64 `json:"fallbackDecisions,omitempty"`
	// AutomatedDecisions counts gameplay decisions a bot made ON THIS SEAT
	// while it was automated (a human seat covered by a bot after a
	// disconnect / no-show). Pure human play has automatedDecisions == 0.
	AutomatedDecisions uint64 `json:"automatedDecisions,omitempty"`
}

type PaipuAction struct {
	Act   string   `json:"act"`
	Seat  uint32   `json:"seat"`
	Tile  *int     `json:"tile,omitempty"`  // tile ID (pointer to handle tile 0 = 1s correctly)
	Tiles []uint32 `json:"tiles,omitempty"` // tile IDs for meld actions
	From  *int     `json:"from,omitempty"`  // discarder seat (pointer to handle seat 0 correctly)
}

// IntPtr creates an int pointer for PaipuAction fields.
func IntPtr(v int) *int { return &v }

// PaipuCheckpoint identifies the exact model that served a remote decision.
// Captured atomically from the same /act response that produced the action.
type PaipuCheckpoint struct {
	Name   string `json:"name"`             // checkpoint file base name
	Step   int64  `json:"step"`             // training step
	Sha256 string `json:"sha256,omitempty"` // empty when the server predates sha reporting
}

// PaipuDecision is one row of the v2 supervision trace: a player decision
// with its full legal-action context and provenance. It is SEPARATE from the
// Actions replay stream (which stays canonical and pass-free); replay
// consumers cross-check the two (internal/review).
type PaipuDecision struct {
	Index int    `json:"index"` // monotonic within the round, assigned by the recorder
	Seat  uint32 `json:"seat"`
	// ChosenID/LegalIDs are catalog action IDs (internal/rl action catalog,
	// pinned by Paipu.ActionCatalogVersion). NEVER omitempty: id 0 is PASS.
	ChosenID int   `json:"chosenId"`
	LegalIDs []int `json:"legalIds"`
	// LegalIDsError marks a row whose legal-set snapshot failed at record
	// time (LegalIDs is then nil). Live play never blocks on snapshot errors.
	LegalIDsError  bool             `json:"legalIdsError,omitempty"`
	Source         string           `json:"source"` // "human" | "remote" | "fallback" | "heuristic"
	FallbackReason string           `json:"fallbackReason,omitempty"`
	Checkpoint     *PaipuCheckpoint `json:"checkpoint,omitempty"` // remote decisions only
}

type PaipuFlowerReveal struct {
	Seat        uint32 `json:"seat"`
	Flower      uint32 `json:"flower"`      // tile ID of flower
	Replacement uint32 `json:"replacement"` // tile ID of replacement drawn
}

type PaipuMeld struct {
	Type  string   `json:"type"`           // "chii", "pon", "kan"
	Tiles []uint32 `json:"tiles"`          // tile IDs in the meld
	From  int      `json:"from,omitempty"` // discarder seat; -1 for closed kan
}

type PaipuBreakdown struct {
	// Id is the stable pattern identifier (ScoreEntry.pattern_id). Empty in
	// paipu recorded before it existed; Name remains the display fallback.
	Id     string `json:"id,omitempty"`
	Name   string `json:"name"`
	Points int32  `json:"points"`
}

type PaipuRoundResult struct {
	Type         string           `json:"type"`              // "win" or "draw"
	Winner       *int             `json:"winner"`            // seat (pointer: seat 0 is valid); nil for draw
	WinType      string           `json:"winType,omitempty"` // "tsumo" or "ron"
	Discarder    *int             `json:"discarder"`         // seat (pointer); nil for tsumo/draw
	WinTile      *int             `json:"winTile,omitempty"` // tile ID (pointer: tile 0 is valid)
	Hand         []uint32         `json:"hand,omitempty"`    // winning hand tile IDs
	Melds        []PaipuMeld      `json:"melds,omitempty"`   // open melds
	Flowers      []uint32         `json:"flowers,omitempty"` // flower tile IDs
	Breakdown    []PaipuBreakdown `json:"breakdown,omitempty"`
	TotalScore   int32            `json:"totalScore,omitempty"`
	ScoreChanges []int32          `json:"scoreChanges"` // length 4, per-seat delta
}

type PaipuRound struct {
	Round          uint32              `json:"round"`
	PrevailingWind uint32              `json:"prevailingWind"`
	Dealer         uint32              `json:"dealer"`
	Dice           [2]uint32           `json:"dice"`
	WallSeed       string              `json:"wallSeed"`
	WildTiles      []PaipuTile         `json:"wildTiles"`
	WangpaiStacks  uint32              `json:"wangpaiStacks"`
	StartingScores [4]int32            `json:"startingScores"`
	Deals          [4][]uint32         `json:"deals"`          // 4 arrays of 13 tile IDs each
	InitialFlowers []PaipuFlowerReveal `json:"initialFlowers"` // auto-revealed during deal
	Actions        []PaipuAction       `json:"actions"`
	Result         *PaipuRoundResult   `json:"result"`
	Decisions      []PaipuDecision     `json:"decisions,omitempty"`
}

// Paipu version + proto-enum provenance constants.
const (
	// PaipuVersion is the schema version written by this recorder.
	// v2 (2026-08-09) added the Decisions supervision trace + match metadata.
	PaipuVersion = 2
	// ProtoEnumsRevision guards the raw proto enum ints embedded in paipu
	// JSON (PaipuTile.Suit). Bump if proto/game.proto ever renumbers an enum
	// a paipu embeds — historical records are only interpretable against the
	// revision they were written with.
	ProtoEnumsRevision = 1
)

type Paipu struct {
	Version     int           `json:"version"`
	MatchID     string        `json:"matchId"`
	Ruleset     string        `json:"ruleset"`
	Players     []PaipuPlayer `json:"players"`
	Rounds      []PaipuRound  `json:"rounds"`
	FinalScores [4]int32      `json:"finalScores"`

	// v2 match metadata (empty/nil in v1 records — readers treat absence as
	// unknown). Set once at persist time via SetMatchMeta.
	Status               string              `json:"status,omitempty"`           // "completed" | "aborted"
	CompletionReason     string              `json:"completionReason,omitempty"` // "match_end" | "drained" | "abandoned"
	Placements           *[4]uint            `json:"placements,omitempty"`       // competition ranking, ties share best
	ServerCommit         string              `json:"serverCommit,omitempty"`
	MatchMode            string              `json:"matchMode,omitempty"` // "classic" | "chongci"
	Chongci              *PaipuChongciConfig `json:"chongci,omitempty"`
	RulesetVersion       string              `json:"rulesetVersion,omitempty"`
	EventContractVersion uint32              `json:"eventContractVersion,omitempty"`
	ProtoEnumsRevision   int                 `json:"protoEnumsRevision,omitempty"`
	ActionCatalogVersion int                 `json:"actionCatalogVersion,omitempty"`
}

// PaipuChongciConfig mirrors the pb.ChongciConfig the match ran under.
type PaipuChongciConfig struct {
	StartingScore int32  `json:"startingScore"`
	BustThreshold int32  `json:"bustThreshold"`
	MaxHands      uint32 `json:"maxHands"`
}

// PaipuMatchMeta carries the v2 header fields set at persist time.
type PaipuMatchMeta struct {
	Status               string
	CompletionReason     string
	Placements           *[4]uint
	ServerCommit         string
	MatchMode            string
	Chongci              *PaipuChongciConfig
	RulesetVersion       string
	EventContractVersion uint32
	ProtoEnumsRevision   int
	ActionCatalogVersion int
}

// TileFromId converts a tile ID (0-143) to its suit and value.
// Layout mirrors rules/fh.go GetInitialWall():
//
//	  0-35: SOU 1-9 (4 copies each)
//	 36-71: MAN 1-9 (4 copies each)
//	72-107: PIN 1-9 (4 copies each)
//	108-135: JIHAI 1-7 (4 copies each)
//	136-143: FLOWER 1-8 (1 each)
func TileFromId(id uint32) (pb.Suit, uint32) {
	switch {
	case id < 36:
		return pb.Suit_SUIT_SOU, (id / 4) + 1
	case id < 72:
		return pb.Suit_SUIT_MAN, ((id - 36) / 4) + 1
	case id < 108:
		return pb.Suit_SUIT_PIN, ((id - 72) / 4) + 1
	case id < 136:
		return pb.Suit_SUIT_JIHAI, ((id - 108) / 4) + 1
	default:
		return pb.Suit_SUIT_FLOWER, (id - 136) + 1
	}
}

// PaipuRecorder accumulates game events into a structured Paipu.
type PaipuRecorder struct {
	paipu        Paipu
	currentRound *PaipuRound
}

func NewPaipuRecorder(matchID, ruleset string) *PaipuRecorder {
	return &PaipuRecorder{
		paipu: Paipu{
			Version: PaipuVersion,
			MatchID: matchID,
			Ruleset: ruleset,
		},
	}
}

func (r *PaipuRecorder) AddPlayer(seat uint32, name string, userID uint) {
	r.AddPlayerInfo(PaipuPlayer{
		Seat:   seat,
		Name:   name,
		UserID: userID,
	})
}

// AddPlayerInfo records a seat entry with full composition labels
// (kind/difficulty/policy identity). AddPlayer remains for callers that
// don't know the seat composition.
func (r *PaipuRecorder) AddPlayerInfo(p PaipuPlayer) {
	r.paipu.Players = append(r.paipu.Players, p)
}

// SetPlayerPolicyID overwrites a seat's recorded policy identity. Used at
// persist time to reconcile the match-start label with the checkpoints that
// actually served the seat's actions (a hot reload mid-match adds entries).
func (r *PaipuRecorder) SetPlayerPolicyID(seat uint32, policyID string) {
	for i := range r.paipu.Players {
		if r.paipu.Players[i].Seat == seat {
			r.paipu.Players[i].PolicyID = policyID
			return
		}
	}
}

// SetPlayerDecisionCounts records a seat's remote-vs-fallback decision
// provenance at persist time.
func (r *PaipuRecorder) SetPlayerDecisionCounts(seat uint32, remote, fallback uint64) {
	for i := range r.paipu.Players {
		if r.paipu.Players[i].Seat == seat {
			r.paipu.Players[i].RemoteDecisions = remote
			r.paipu.Players[i].FallbackDecisions = fallback
			return
		}
	}
}

// SetPlayerAutomatedDecisions records how many gameplay decisions were made
// by automation on this seat (bot takeover of a human seat).
func (r *PaipuRecorder) SetPlayerAutomatedDecisions(seat uint32, count uint64) {
	for i := range r.paipu.Players {
		if r.paipu.Players[i].Seat == seat {
			r.paipu.Players[i].AutomatedDecisions = count
			return
		}
	}
}

func (r *PaipuRecorder) StartRound(
	round, prevailingWind, dealer uint32,
	dice [2]uint32,
	wallSeed string,
	wildTiles []*pb.Tile,
	wangpaiStacks uint32,
	startingScores [4]int32,
	deals [4][]uint32,
) {
	wt := make([]PaipuTile, len(wildTiles))
	for i, t := range wildTiles {
		wt[i] = PaipuTile{ID: t.Id, Suit: t.Suit, Value: t.Value}
	}
	r.currentRound = &PaipuRound{
		Round:          round,
		PrevailingWind: prevailingWind,
		Dealer:         dealer,
		Dice:           dice,
		WallSeed:       wallSeed,
		WildTiles:      wt,
		WangpaiStacks:  wangpaiStacks,
		StartingScores: startingScores,
		Deals:          deals,
		Actions:        make([]PaipuAction, 0),
	}
}

func (r *PaipuRecorder) RecordInitialFlower(seat, flowerTileID, replacementTileID uint32) {
	if r.currentRound == nil {
		return
	}
	r.currentRound.InitialFlowers = append(r.currentRound.InitialFlowers, PaipuFlowerReveal{
		Seat:        seat,
		Flower:      flowerTileID,
		Replacement: replacementTileID,
	})
}

func (r *PaipuRecorder) record(a PaipuAction) {
	if r.currentRound == nil {
		return
	}
	r.currentRound.Actions = append(r.currentRound.Actions, a)
}

func (r *PaipuRecorder) RecordDraw(seat uint32, tileID uint32) {
	r.record(PaipuAction{Act: "draw", Seat: seat, Tile: IntPtr(int(tileID))})
}

func (r *PaipuRecorder) RecordDiscard(seat uint32, tileID uint32) {
	r.record(PaipuAction{Act: "discard", Seat: seat, Tile: IntPtr(int(tileID))})
}

func (r *PaipuRecorder) RecordChii(seat uint32, handTileIDs []uint32, fromSeat uint32) {
	r.record(PaipuAction{Act: "chii", Seat: seat, Tiles: handTileIDs, From: IntPtr(int(fromSeat))})
}

func (r *PaipuRecorder) RecordPon(seat uint32, handTileIDs []uint32, fromSeat uint32) {
	r.record(PaipuAction{Act: "pon", Seat: seat, Tiles: handTileIDs, From: IntPtr(int(fromSeat))})
}

func (r *PaipuRecorder) RecordOpenKan(seat uint32, handTileIDs []uint32, fromSeat uint32) {
	r.record(PaipuAction{Act: "okan", Seat: seat, Tiles: handTileIDs, From: IntPtr(int(fromSeat))})
}

func (r *PaipuRecorder) RecordClosedKan(seat uint32, tileIDs []uint32) {
	r.record(PaipuAction{Act: "ckan", Seat: seat, Tiles: tileIDs})
}

func (r *PaipuRecorder) RecordUpgradeKan(seat uint32, tileID uint32) {
	r.record(PaipuAction{Act: "ukan", Seat: seat, Tile: IntPtr(int(tileID))})
}

func (r *PaipuRecorder) RecordFlowerReveal(seat uint32, tileID uint32) {
	r.record(PaipuAction{Act: "flower", Seat: seat, Tile: IntPtr(int(tileID))})
}

func (r *PaipuRecorder) RecordTsumo(seat uint32, tileID uint32) {
	r.record(PaipuAction{Act: "tsumo", Seat: seat, Tile: IntPtr(int(tileID))})
}

func (r *PaipuRecorder) RecordRon(seat uint32, tileID uint32, fromSeat uint32) {
	r.record(PaipuAction{Act: "ron", Seat: seat, Tile: IntPtr(int(tileID)), From: IntPtr(int(fromSeat))})
}

func (r *PaipuRecorder) RecordHaiteiAccept(seat uint32, tileID uint32) {
	r.record(PaipuAction{Act: "haitei", Seat: seat, Tile: IntPtr(int(tileID))})
}

func (r *PaipuRecorder) RecordHaiteiRefuse(seat uint32) {
	r.record(PaipuAction{Act: "haiteiRefuse", Seat: seat})
}

// RecordDecision appends a supervision-trace row to the current round,
// assigning its monotonic per-round index. No-op between rounds (mirrors
// record()); callers snapshot legal IDs BEFORE processing the action and
// call this only AFTER the action succeeded.
func (r *PaipuRecorder) RecordDecision(d PaipuDecision) {
	if r.currentRound == nil {
		return
	}
	d.Index = len(r.currentRound.Decisions)
	r.currentRound.Decisions = append(r.currentRound.Decisions, d)
}

// SetMatchMeta stamps the v2 match-level header fields. Called at persist
// time (idempotent — persistMatch may run more than once for snapshots).
func (r *PaipuRecorder) SetMatchMeta(m PaipuMatchMeta) {
	p := &r.paipu
	p.Status = m.Status
	p.CompletionReason = m.CompletionReason
	p.Placements = m.Placements
	p.ServerCommit = m.ServerCommit
	p.MatchMode = m.MatchMode
	p.Chongci = m.Chongci
	p.RulesetVersion = m.RulesetVersion
	p.EventContractVersion = m.EventContractVersion
	p.ProtoEnumsRevision = m.ProtoEnumsRevision
	p.ActionCatalogVersion = m.ActionCatalogVersion
}

func (r *PaipuRecorder) EndRound(result *PaipuRoundResult) {
	if r.currentRound == nil {
		return
	}
	r.currentRound.Result = result
	r.paipu.Rounds = append(r.paipu.Rounds, *r.currentRound)
	r.currentRound = nil
}

func (r *PaipuRecorder) Finalize(finalScores [4]int32) *Paipu {
	r.paipu.FinalScores = finalScores
	return &r.paipu
}

// Snapshot returns a copy of the paipu that ALSO includes the in-progress
// round (with a nil Result), so an aborted match persists the active hand's
// deals and actions instead of dropping them. Unlike Finalize it never
// mutates recorder state beyond the returned copy; the current round can
// still end normally afterwards. Call from the goroutine that owns the
// recorder (the round's Actions and Decisions slices are shared with the
// copy).
func (r *PaipuRecorder) Snapshot(finalScores [4]int32) *Paipu {
	snap := r.paipu
	snap.FinalScores = finalScores
	snap.Rounds = make([]PaipuRound, len(r.paipu.Rounds), len(r.paipu.Rounds)+1)
	copy(snap.Rounds, r.paipu.Rounds)
	if r.currentRound != nil {
		partial := *r.currentRound
		partial.Result = nil
		snap.Rounds = append(snap.Rounds, partial)
	}
	return &snap
}

// CurrentRound returns the in-progress round (for testing).
func (r *PaipuRecorder) CurrentRound() *PaipuRound {
	return r.currentRound
}
