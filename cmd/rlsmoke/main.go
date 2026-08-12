// Command rlsmoke drives the paipu-v2 provenance rollout-gate smoke against a
// LIVE server (local or production): it registers a throwaway account, creates
// a private table, seats RL agents in every empty seat, starts a classic
// (single-hand) match, plays the host seat over the real WebSocket protocol
// with the shared heuristic bot, waits for PHASE_MATCH_END, and then verifies
// the persisted paipu: version 2, decision rows with legal-id sets, explicit
// pass rows, per-decision RL provenance (remote source + checkpoint sha256),
// and status "completed". It also requires the match to appear under
// /users/me/replays, which reads the matches table — evidence the DB row (not
// just the in-memory paipu store) persisted with MATCH_END.
//
// Exit 0 = every gate check passed. Any other exit means the rollout gate is
// NOT satisfied and shadow-game accumulation must not resume.
package main

import (
	"bytes"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/http/cookiejar"
	"net/url"
	"strings"
	"time"

	"github.com/gorilla/websocket"
	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/proto"

	"github.com/plasma/fh-mahjong/internal/bot"
	"github.com/plasma/fh-mahjong/internal/engine"
	pb "github.com/plasma/fh-mahjong/proto"
)

func main() {
	baseURL := flag.String("base-url", "http://localhost:8080", "server base URL (http/https)")
	mode := flag.String("mode", "classic", "match mode for the smoke table (classic = single hand, fastest)")
	timeout := flag.Duration("timeout", 10*time.Minute, "overall deadline for the whole smoke")
	flag.Parse()

	if err := run(*baseURL, *mode, *timeout); err != nil {
		log.Fatalf("SMOKE FAILED: %v", err)
	}
	fmt.Println("SMOKE PASSED")
}

func run(baseURL, mode string, timeout time.Duration) error {
	deadline := time.Now().Add(timeout)
	jar, err := cookiejar.New(nil)
	if err != nil {
		return err
	}
	client := &http.Client{Jar: jar, Timeout: 30 * time.Second}
	suffix := randomHex(6)

	// 1. Throwaway account (guests are full authenticated users in this app).
	// The register response carries the session's CSRF token, required as
	// X-CSRF-Token on every subsequent mutating request.
	username := "smoke_" + suffix
	var auth struct {
		CSRFToken string `json:"csrfToken"`
	}
	if err := postJSON(client, baseURL+"/api/v1/auth/register", map[string]any{
		"email":    "smoke-" + suffix + "@fh-mahjong.invalid",
		"username": username,
		"password": "smoke-" + randomHex(12),
	}, &auth); err != nil {
		return fmt.Errorf("register: %w", err)
	}
	if auth.CSRFToken == "" {
		return fmt.Errorf("register response carried no csrfToken")
	}
	csrfToken = auth.CSRFToken

	// 2. Private table; find the host's own seat from the returned config.
	var table pb.PrivateTableState
	if err := postProtoJSON(client, baseURL+"/api/v1/rooms", map[string]any{}, &table); err != nil {
		return fmt.Errorf("create room: %w", err)
	}
	mySeat, found := seatOfHuman(&table, username)
	if !found {
		return fmt.Errorf("create room: host seat not found in table %s", table.TableId)
	}
	log.Printf("table %s created; host seat %d", table.TableId, mySeat)

	if err := postJSON(client, baseURL+"/api/v1/rooms/"+table.TableId+"/mode",
		map[string]any{"mode": mode}, nil); err != nil {
		return fmt.Errorf("set mode %s: %w", mode, err)
	}

	// 3. RL agents in every empty seat. This exercises the health-gated
	// policy resolution — a down policy service fails the smoke here.
	for i, seat := range table.Seats {
		if seat.GetKind() != "empty" {
			continue
		}
		if err := postJSON(client, baseURL+"/api/v1/rooms/"+table.TableId+"/seat", map[string]any{
			"seat": i, "kind": "bot", "difficulty": int(pb.Difficulty_DIFFICULTY_RL),
		}, nil); err != nil {
			return fmt.Errorf("seat RL agent at %d: %w", i, err)
		}
		log.Printf("seat %d: RL agent", i)
	}

	// 4. Connect the host's WebSocket BEFORE starting: an all-humans-offline
	// room ends (and persists "aborted") the moment the last human drops, so
	// the socket must be live for the whole match.
	wsConn, err := dialWS(baseURL, jar)
	if err != nil {
		return fmt.Errorf("websocket dial: %w", err)
	}
	defer wsConn.Close()

	var started pb.PrivateTableState
	if err := postProtoJSON(client, baseURL+"/api/v1/rooms/"+table.TableId+"/start",
		map[string]any{}, &started); err != nil {
		return fmt.Errorf("start: %w", err)
	}
	log.Printf("match %s started (mode %s)", started.MatchId, mode)

	// 5. Play the host seat to MATCH_END.
	matchID, err := playToMatchEnd(wsConn, mySeat, deadline)
	if err != nil {
		return fmt.Errorf("play: %w", err)
	}
	if started.MatchId != "" && matchID != started.MatchId {
		return fmt.Errorf("match id drift: started %s but played %s", started.MatchId, matchID)
	}
	log.Printf("match %s reached PHASE_MATCH_END", matchID)

	// 6. DB persistence: the match must list under /users/me/replays (reads
	// the matches table; only completed MATCH_END rows appear).
	if err := waitForReplayListing(client, baseURL, matchID, deadline); err != nil {
		return err
	}

	// 7. Fetch the paipu and verify the v2 provenance gates.
	report, err := verifyPaipu(client, baseURL, matchID)
	if err != nil {
		return err
	}
	fmt.Println(report)
	return nil
}

func randomHex(n int) string {
	buf := make([]byte, n)
	if _, err := rand.Read(buf); err != nil {
		panic(err)
	}
	return hex.EncodeToString(buf)
}

// csrfToken is the session's CSRF token, captured at register time and sent
// on every mutating request (the server rejects POSTs without it).
var csrfToken string

func postJSON(client *http.Client, url string, body any, out any) error {
	payload, err := json.Marshal(body)
	if err != nil {
		return err
	}
	req, err := http.NewRequest(http.MethodPost, url, bytes.NewReader(payload))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	if csrfToken != "" {
		req.Header.Set("X-CSRF-Token", csrfToken)
	}
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	data, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("%s -> %d: %s", url, resp.StatusCode, strings.TrimSpace(string(data)))
	}
	if out != nil {
		return json.Unmarshal(data, out)
	}
	return nil
}

// postProtoJSON posts like postJSON but decodes the response with protojson
// (the private-table endpoints emit protojson with numeric enums).
func postProtoJSON(client *http.Client, url string, body any, out proto.Message) error {
	var raw json.RawMessage
	if err := postJSON(client, url, body, &raw); err != nil {
		return err
	}
	return protojson.UnmarshalOptions{DiscardUnknown: true}.Unmarshal(raw, out)
}

func seatOfHuman(table *pb.PrivateTableState, username string) (uint32, bool) {
	for i, seat := range table.Seats {
		if seat.GetKind() == "human" && seat.GetUsername() == username {
			return uint32(i), true
		}
	}
	return 0, false
}

func dialWS(baseURL string, jar http.CookieJar) (*websocket.Conn, error) {
	u, err := url.Parse(baseURL)
	if err != nil {
		return nil, err
	}
	switch u.Scheme {
	case "http":
		u.Scheme = "ws"
	case "https":
		u.Scheme = "wss"
	default:
		return nil, fmt.Errorf("unsupported scheme %q", u.Scheme)
	}
	u.Path = "/api/v1/ws"
	dialer := websocket.Dialer{Jar: jar, HandshakeTimeout: 15 * time.Second}
	// No Origin header: the server allows origin-less (non-browser) clients.
	conn, resp, err := dialer.Dial(u.String(), nil)
	if resp != nil && resp.Body != nil {
		resp.Body.Close()
	}
	return conn, err
}

// playToMatchEnd reacts to every broadcast GameState exactly the way the
// server's own bot pump does for automated seats: heuristic action on our
// turn or claim window, READY at round end, done at match end. Text frames
// are lobby/control JSON and are skipped.
func playToMatchEnd(conn *websocket.Conn, seat uint32, deadline time.Time) (string, error) {
	policy := bot.NewHeuristicPolicy()
	sentReady := false
	matchID := ""
	for {
		if time.Now().After(deadline) {
			return "", fmt.Errorf("deadline exceeded before MATCH_END (last match id %q)", matchID)
		}
		conn.SetReadDeadline(time.Now().Add(90 * time.Second))
		frameType, payload, err := conn.ReadMessage()
		if err != nil {
			return "", fmt.Errorf("read (last match id %q): %w", matchID, err)
		}
		if frameType != websocket.BinaryMessage {
			continue
		}
		var state pb.GameState
		if err := proto.Unmarshal(payload, &state); err != nil {
			log.Printf("skipping undecodable binary frame: %v", err)
			continue
		}
		if state.MatchId != "" {
			matchID = state.MatchId
		}
		switch state.Phase {
		case pb.GamePhase_PHASE_MATCH_END:
			return matchID, nil
		case pb.GamePhase_PHASE_ROUND_END:
			if !sentReady {
				if err := sendAction(conn, &pb.PlayerAction{Type: pb.ActionType_ACTION_READY}); err != nil {
					return "", err
				}
				sentReady = true
			}
		default:
			sentReady = false
			if action := policy.ChooseAction(&state, seat); action != nil {
				if err := sendAction(conn, action); err != nil {
					return "", err
				}
			}
		}
	}
}

func sendAction(conn *websocket.Conn, action *pb.PlayerAction) error {
	payload, err := proto.Marshal(action)
	if err != nil {
		return err
	}
	conn.SetWriteDeadline(time.Now().Add(15 * time.Second))
	return conn.WriteMessage(websocket.BinaryMessage, payload)
}

func waitForReplayListing(client *http.Client, baseURL, matchID string, deadline time.Time) error {
	type replayRow struct {
		MatchID string `json:"matchId"`
	}
	var listing struct {
		Replays []replayRow `json:"replays"`
	}
	for {
		if err := getJSON(client, baseURL+"/api/v1/users/me/replays?limit=20", &listing); err != nil {
			return fmt.Errorf("list replays: %w", err)
		}
		for _, row := range listing.Replays {
			if row.MatchID == matchID {
				log.Printf("match %s listed under /users/me/replays (matches table persisted)", matchID)
				return nil
			}
		}
		if time.Now().After(deadline) {
			return fmt.Errorf("match %s never appeared under /users/me/replays — DB row missing or not completed", matchID)
		}
		time.Sleep(2 * time.Second)
	}
}

func getJSON(client *http.Client, url string, out any) error {
	resp, err := client.Get(url)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	data, _ := io.ReadAll(io.LimitReader(resp.Body, 8<<20))
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("%s -> %d: %s", url, resp.StatusCode, strings.TrimSpace(string(data[:min(len(data), 300)])))
	}
	return json.Unmarshal(data, out)
}

// verifyPaipu fetches the persisted paipu and checks every rollout-gate
// requirement from the provenance spec. It returns a human-readable summary
// on success and an error naming the first failed gate otherwise.
func verifyPaipu(client *http.Client, baseURL, matchID string) (string, error) {
	var paipu engine.Paipu
	if err := getJSON(client, baseURL+"/api/v1/replays/"+matchID, &paipu); err != nil {
		return "", fmt.Errorf("fetch paipu: %w", err)
	}
	if paipu.Version != engine.PaipuVersion {
		return "", fmt.Errorf("paipu version = %d, want %d", paipu.Version, engine.PaipuVersion)
	}
	if paipu.Status != "completed" {
		return "", fmt.Errorf("paipu status = %q, want \"completed\"", paipu.Status)
	}
	var total, passRows, remoteRows, remoteWithSha, humanRows, legalErrs int
	shas := map[string]bool{}
	for _, round := range paipu.Rounds {
		for _, d := range round.Decisions {
			total++
			if d.LegalIDsError {
				legalErrs++
			} else {
				if len(d.LegalIDs) == 0 {
					return "", fmt.Errorf("decision round=%d index=%d seat=%d has empty legalIds without legalIdsError", round.Round, d.Index, d.Seat)
				}
				if !containsInt(d.LegalIDs, d.ChosenID) {
					return "", fmt.Errorf("decision round=%d index=%d seat=%d chosenId %d not in legalIds", round.Round, d.Index, d.Seat, d.ChosenID)
				}
				if d.ChosenID == 0 {
					passRows++
				}
			}
			switch d.Source {
			case "remote":
				remoteRows++
				if d.Checkpoint != nil && d.Checkpoint.Sha256 != "" {
					remoteWithSha++
					shas[d.Checkpoint.Sha256] = true
				}
			case "human":
				humanRows++
			}
		}
	}
	if total == 0 {
		return "", fmt.Errorf("paipu has no decision rows — v2 trace missing")
	}
	if remoteRows == 0 {
		return "", fmt.Errorf("no remote (RL) decision rows — RL seats did not play via the policy service")
	}
	if remoteWithSha != remoteRows {
		return "", fmt.Errorf("%d of %d remote decisions lack a checkpoint sha256", remoteRows-remoteWithSha, remoteRows)
	}
	if humanRows == 0 {
		return "", fmt.Errorf("no human decision rows — host seat decisions were not traced")
	}
	if passRows == 0 {
		return "", fmt.Errorf("no explicit pass rows (chosenId 0) — pass tracing missing")
	}
	if legalErrs > 0 {
		return "", fmt.Errorf("%d decision rows carry legalIdsError — legal-set snapshotting failed in production", legalErrs)
	}
	shaList := make([]string, 0, len(shas))
	for sha := range shas {
		shaList = append(shaList, sha[:min(len(sha), 12)])
	}
	return fmt.Sprintf(
		"paipu v2 gates OK for %s: decisions=%d (remote=%d human=%d pass=%d), remote sha256(s)=%s, status=completed, serverCommit=%s, catalog=%d",
		matchID, total, remoteRows, humanRows, passRows, strings.Join(shaList, ","),
		paipu.ServerCommit, paipu.ActionCatalogVersion), nil
}

func containsInt(list []int, v int) bool {
	for _, x := range list {
		if x == v {
			return true
		}
	}
	return false
}
