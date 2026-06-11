# Game-table Exit & Rejoin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a top-right Exit button to the in-play game table that, after confirmation, returns the player to the waiting room while a bot plays their seat, and lets them rejoin from a Rejoin banner or a cross-device rejoin link.

**Architecture:** Frontend-only. The Go server already plays any seat with no connected websocket as a bot (`api/room.go` `isAutomatedSeat`) and reclaims a seat on websocket reconnect by matching the JWT user id (`api/ws.go:81-101`). The frontend exits by closing the socket and navigating to `/room/:roomId`, while a `left-match` marker in `sessionStorage` stops the waiting room from auto-reconnecting and bouncing the player back. Rejoin re-opens the socket and navigates back into the match. A cross-device rejoin link carries the guest JWT in the room URL (`?token=<jwt>`).

**Tech Stack:** React 19 + TypeScript, react-router-dom 7, Vite, Vitest (node env, pure-function `.test.ts` files), Tailwind utility classes for overlays.

**Spec:** `docs/superpowers/specs/2026-06-10-game-table-exit-rejoin-design.md`

---

## File Structure

- **Create:** `web/src/pages/rejoinMatch.ts` — pure helpers (rejoin-link build/parse, `left-match` marker serialize/parse) plus thin `sessionStorage` wrappers for the marker. Mirrors the existing `privateRoomSession.ts` module style.
- **Create:** `web/src/pages/rejoinMatch.test.ts` — Vitest unit tests for the pure helpers (node env, no DOM).
- **Create:** `web/src/pages/ExitMatchButton.tsx` — the corner Exit button + confirmation modal (presentational; calls back to the parent to perform the leave). Built with Tailwind utility classes, matching `MatchEndOverlay.tsx`.
- **Modify:** `web/src/pages/Game.tsx` — render `<ExitMatchButton>` inside `game-stage-shell`, wire the leave action (write marker, close socket, navigate to room).
- **Modify:** `web/src/pages/Table.tsx` — consume `?token=` rejoin links, suppress auto-connect/auto-redirect when the marker is set, render the Rejoin banner, and implement Rejoin.

No backend changes. The seat handoff is already covered by `api/room_bot_test.go`.

---

## Task 1: Pure rejoin/marker helpers (`rejoinMatch.ts`)

**Files:**
- Create: `web/src/pages/rejoinMatch.ts`
- Test: `web/src/pages/rejoinMatch.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `web/src/pages/rejoinMatch.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import {
  buildRejoinLink,
  extractRejoinToken,
  stripTokenFromUrl,
  parseLeftMatchMarker,
  serializeLeftMatchMarker,
} from './rejoinMatch'

describe('buildRejoinLink', () => {
  it('builds a room URL carrying the token', () => {
    expect(buildRejoinLink('https://app.test', 'ROOM42', 'jwt.abc')).toBe(
      'https://app.test/room/ROOM42?token=jwt.abc',
    )
  })

  it('url-encodes the room id and token', () => {
    expect(buildRejoinLink('https://app.test', 'a b', 'x/y')).toBe(
      'https://app.test/room/a%20b?token=x%2Fy',
    )
  })

  it('drops a trailing slash on the origin', () => {
    expect(buildRejoinLink('https://app.test/', 'R', 't')).toBe(
      'https://app.test/room/R?token=t',
    )
  })
})

describe('extractRejoinToken', () => {
  it('reads the token query param', () => {
    expect(extractRejoinToken('?token=jwt.abc')).toBe('jwt.abc')
  })

  it('returns null when there is no token', () => {
    expect(extractRejoinToken('?foo=bar')).toBeNull()
    expect(extractRejoinToken('')).toBeNull()
  })

  it('returns null for an empty token value', () => {
    expect(extractRejoinToken('?token=')).toBeNull()
  })
})

describe('stripTokenFromUrl', () => {
  it('removes the token param but keeps the path and other params', () => {
    expect(stripTokenFromUrl('https://app.test/room/R?token=jwt.abc&x=1')).toBe(
      'https://app.test/room/R?x=1',
    )
  })

  it('leaves no trailing question mark when token was the only param', () => {
    expect(stripTokenFromUrl('https://app.test/room/R?token=jwt.abc')).toBe(
      'https://app.test/room/R',
    )
  })

  it('is a no-op when there is no token param', () => {
    expect(stripTokenFromUrl('https://app.test/room/R')).toBe(
      'https://app.test/room/R',
    )
  })
})

describe('left-match marker serialization', () => {
  it('round-trips a marker', () => {
    const raw = serializeLeftMatchMarker({ roomId: 'R', matchId: 'M' })
    expect(parseLeftMatchMarker(raw)).toEqual({ roomId: 'R', matchId: 'M' })
  })

  it('returns null for null / malformed / incomplete input', () => {
    expect(parseLeftMatchMarker(null)).toBeNull()
    expect(parseLeftMatchMarker('not json')).toBeNull()
    expect(parseLeftMatchMarker('{"roomId":"R"}')).toBeNull()
    expect(parseLeftMatchMarker('{"matchId":"M"}')).toBeNull()
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd web && npx vitest run src/pages/rejoinMatch.test.ts`
Expected: FAIL — `Failed to resolve import "./rejoinMatch"` / functions not defined.

- [ ] **Step 3: Implement the module**

Create `web/src/pages/rejoinMatch.ts`:

```ts
export type LeftMatchMarker = {
  roomId: string
  matchId: string
}

const LEFT_MATCH_KEY = 'mahjong_left_match_v1'

// ---- pure helpers (unit-tested) -------------------------------------------

export function buildRejoinLink(origin: string, roomId: string, token: string): string {
  const base = origin.replace(/\/+$/, '')
  return `${base}/room/${encodeURIComponent(roomId)}?token=${encodeURIComponent(token)}`
}

export function extractRejoinToken(search: string): string | null {
  const params = new URLSearchParams(search)
  const token = params.get('token')
  return token && token.length > 0 ? token : null
}

export function stripTokenFromUrl(href: string): string {
  const url = new URL(href)
  url.searchParams.delete('token')
  const query = url.searchParams.toString()
  return `${url.origin}${url.pathname}${query ? `?${query}` : ''}${url.hash}`
}

export function serializeLeftMatchMarker(marker: LeftMatchMarker): string {
  return JSON.stringify({ roomId: marker.roomId, matchId: marker.matchId })
}

export function parseLeftMatchMarker(raw: string | null): LeftMatchMarker | null {
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as Partial<LeftMatchMarker>
    if (typeof parsed.roomId === 'string' && typeof parsed.matchId === 'string') {
      return { roomId: parsed.roomId, matchId: parsed.matchId }
    }
    return null
  } catch {
    return null
  }
}

// ---- sessionStorage wrappers (guarded, mirror privateRoomSession.ts) -------

function getSessionStorage(): Storage | null {
  if (typeof window === 'undefined') return null
  return window.sessionStorage
}

export function saveLeftMatchMarker(marker: LeftMatchMarker): void {
  getSessionStorage()?.setItem(LEFT_MATCH_KEY, serializeLeftMatchMarker(marker))
}

export function loadLeftMatchMarker(): LeftMatchMarker | null {
  const storage = getSessionStorage()
  if (!storage) return null
  return parseLeftMatchMarker(storage.getItem(LEFT_MATCH_KEY))
}

export function clearLeftMatchMarker(): void {
  getSessionStorage()?.removeItem(LEFT_MATCH_KEY)
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd web && npx vitest run src/pages/rejoinMatch.test.ts`
Expected: PASS — all assertions green.

- [ ] **Step 5: Commit**

```bash
git add web/src/pages/rejoinMatch.ts web/src/pages/rejoinMatch.test.ts
git commit -m "feat(web): rejoin-link and left-match marker helpers"
```

---

## Task 2: Exit button + confirmation modal (`ExitMatchButton.tsx`)

**Files:**
- Create: `web/src/pages/ExitMatchButton.tsx`

This is a React UI component. Following the codebase convention (node-env Vitest tests only cover pure functions; React UI is verified by `tsc` build + preview), there is no unit test for this component. It is verified by the TypeScript build in Step 3 and by the preview run in Task 4.

- [ ] **Step 1: Create the component**

Create `web/src/pages/ExitMatchButton.tsx`:

```tsx
import { useState } from 'react'
import { loadPrivateRoomSession } from './privateRoomSession'
import { buildRejoinLink } from './rejoinMatch'

type Props = {
  roomId: string
  onConfirmLeave: () => void
}

// Top-right Exit control for the in-play game table. Opens a confirmation
// modal so an accidental tap does not drop the player out of the match.
// On confirm it calls onConfirmLeave, which the parent uses to set the
// left-match marker, close the socket, and navigate to the waiting room.
export default function ExitMatchButton({ roomId, onConfirmLeave }: Props) {
  const [open, setOpen] = useState(false)
  const [copied, setCopied] = useState(false)

  const copyLink = async () => {
    const token = loadPrivateRoomSession(roomId)?.token
    if (!token || typeof window === 'undefined') return
    const link = buildRejoinLink(window.location.origin, roomId, token)
    try {
      await navigator.clipboard.writeText(link)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      // Clipboard can be blocked (e.g. insecure context). Fall back to a prompt.
      window.prompt('Copy your rejoin link:', link)
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="absolute right-4 top-4 z-40 rounded-xl border border-white/15 bg-black/40 px-4 py-2 text-xs font-black uppercase tracking-[0.18em] text-white/85 backdrop-blur transition hover:bg-black/60"
        style={{ top: 'calc(env(safe-area-inset-top, 0px) + 1rem)' }}
      >
        Exit
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-6">
          <div className="w-full max-w-md rounded-[28px] border border-emerald-300/20 bg-slate-950/95 p-8 shadow-[0_22px_70px_rgba(0,0,0,0.5)]">
            <h1 className="text-2xl font-black uppercase tracking-[0.12em] text-emerald-100">
              Leave the match?
            </h1>
            <p className="mt-3 text-sm text-slate-300">
              A bot will play your seat while you&apos;re away. You can rejoin
              anytime from the room.
            </p>

            <div className="mt-6 flex flex-col gap-3">
              <button
                type="button"
                onClick={() => { setOpen(false); onConfirmLeave() }}
                className="w-full rounded-2xl border border-rose-300/30 bg-rose-600 px-5 py-3 text-sm font-black uppercase tracking-[0.18em] text-white hover:bg-rose-500"
              >
                Leave
              </button>
              <button
                type="button"
                onClick={copyLink}
                className="w-full rounded-2xl border border-cyan-300/30 bg-cyan-950/60 px-5 py-3 text-sm font-black uppercase tracking-[0.18em] text-cyan-100 hover:bg-cyan-900/70"
              >
                {copied ? 'Link copied' : 'Copy rejoin link'}
              </button>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="w-full rounded-2xl border border-white/15 bg-transparent px-5 py-3 text-sm font-black uppercase tracking-[0.18em] text-white/80 hover:bg-white/5"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
```

- [ ] **Step 2: Verify it type-checks (build)**

Run: `cd web && npx tsc --noEmit`
Expected: PASS — no type errors. (`ExitMatchButton.tsx` is not yet imported anywhere; this only confirms the file itself compiles.)

- [ ] **Step 3: Commit**

```bash
git add web/src/pages/ExitMatchButton.tsx
git commit -m "feat(web): exit button + leave-confirmation modal for game table"
```

---

## Task 3: Wire the Exit button into the game table (`Game.tsx`)

**Files:**
- Modify: `web/src/pages/Game.tsx`

- [ ] **Step 1: Add imports**

At the top of `web/src/pages/Game.tsx`, alongside the existing import of `getPrivateRoomToken`, change the `privateRoomSession` import to also pull in `loadPrivateRoomSession`, and add the marker + component imports.

Find:

```tsx
import { getPrivateRoomToken } from './privateRoomSession';
```

Replace with:

```tsx
import { getPrivateRoomToken, loadPrivateRoomSession } from './privateRoomSession';
import { saveLeftMatchMarker } from './rejoinMatch';
import ExitMatchButton from './ExitMatchButton';
```

- [ ] **Step 2: Add the leave handler inside `GameTable`**

In the `GameTable` function, just before the `return (` of its JSX (right after the `roundResultView` constant, near `Game.tsx:377`), add:

```tsx
    const roomId = loadPrivateRoomSession()?.tableId ?? null;

    const handleLeaveMatch = () => {
        if (roomId && matchId) {
            saveLeftMatchMarker({ roomId, matchId });
        }
        socket?.close();
        navigate(roomId ? `/room/${roomId}` : '/');
    };
```

- [ ] **Step 3: Render the Exit button inside the stage shell**

In `GameTable`'s returned JSX, find the opening of the stage shell (`Game.tsx:380`):

```tsx
        <div className="game-stage-shell" ref={stageLayout.containerRef} style={stageShellStyle}>
```

Immediately after that opening tag (before the `MatchEndOverlay` block), insert:

```tsx
            {gameState?.phase !== 5 && roomId && (
                <ExitMatchButton roomId={roomId} onConfirmLeave={handleLeaveMatch} />
            )}
```

(The button is hidden once the match has ended — phase 5 already shows `MatchEndOverlay` with its own navigation.)

- [ ] **Step 4: Verify it type-checks**

Run: `cd web && npx tsc --noEmit`
Expected: PASS — no type errors.

- [ ] **Step 5: Commit**

```bash
git add web/src/pages/Game.tsx
git commit -m "feat(web): render exit control on the game table and wire leave"
```

---

## Task 4: Suppress auto-redirect + Rejoin banner + cross-device link (`Table.tsx`)

**Files:**
- Modify: `web/src/pages/Table.tsx`

- [ ] **Step 1: Add imports**

At the top of `web/src/pages/Table.tsx`, alongside the existing `privateRoomSession` import, add the marker helpers and rejoin-link helpers. Find:

```tsx
import { clearPrivateRoomSession, loadPrivateRoomSession, savePrivateRoomSession } from './privateRoomSession';
```

After that line add:

```tsx
import {
    buildRejoinLink,
    clearLeftMatchMarker,
    extractRejoinToken,
    loadLeftMatchMarker,
    saveLeftMatchMarker,
    stripTokenFromUrl,
} from './rejoinMatch';
import type { LeftMatchMarker } from './rejoinMatch';
```

- [ ] **Step 2: Add `leftMarker` state and consume a `?token=` rejoin link on mount**

Inside the `Table` component, after the existing `const [rlAgentAvailable, setRlAgentAvailable] = useState(false);` declaration, add:

```tsx
    const [leftMarker, setLeftMarker] = useState<LeftMatchMarker | null>(() => loadLeftMatchMarker());
```

Then, immediately after the `const myUserId = useMyUserId(guestToken);` line, add a mount effect that turns a cross-device rejoin link into a saved session + marker:

```tsx
    // A cross-device rejoin link arrives as /room/:roomId?token=<jwt>. Save the
    // token as our session, strip it from the URL (don't leave a bearer secret
    // in history), and set the left-match marker so the Rejoin banner shows.
    useEffect(() => {
        if (!roomId || typeof window === 'undefined') return;
        const token = extractRejoinToken(window.location.search);
        if (!token) return;

        savePrivateRoomSession({
            tableId: roomId,
            token,
            username: loadPrivateRoomSession(roomId)?.username ?? 'Guest',
        });
        setGuestToken(token);
        window.history.replaceState(null, '', stripTokenFromUrl(window.location.href));

        const marker = { roomId, matchId: '' };
        saveLeftMatchMarker(marker);
        setLeftMarker(marker);
    }, [roomId]);
```

- [ ] **Step 3: Gate auto-redirect and auto-connect on the marker**

Find the redirect effect (`Table.tsx:32-36`):

```tsx
    useEffect(() => {
        if (gameState && gameState.matchId) {
            navigate(`/match/${gameState.matchId}`);
        }
    }, [gameState, navigate]);
```

Replace with:

```tsx
    useEffect(() => {
        if (leftMarker) return; // player intentionally left — show Rejoin, don't bounce back
        if (gameState && gameState.matchId) {
            navigate(`/match/${gameState.matchId}`);
        }
    }, [gameState, navigate, leftMarker]);
```

Find the auto-connect effect (`Table.tsx:38-45`):

```tsx
    useEffect(() => {
        const stored = loadPrivateRoomSession(roomId);
        if (stored && !isConnected) {
            setGuestToken(stored.token);
            setUsername(stored.username);
            connect(stored.token);
        }
    }, [connect, isConnected, roomId]);
```

Replace with:

```tsx
    useEffect(() => {
        if (leftMarker) return; // stay disconnected so the bot keeps our seat
        const stored = loadPrivateRoomSession(roomId);
        if (stored && !isConnected) {
            setGuestToken(stored.token);
            setUsername(stored.username);
            connect(stored.token);
        }
    }, [connect, isConnected, roomId, leftMarker]);
```

- [ ] **Step 4: Guard the lobby_update "started" redirect**

Find, inside the WebSocket message handler (`Table.tsx:107-112`):

```tsx
                if (data.type === 'lobby_update' && data.room === roomId && data.state) {
                    setTableState(data.state as PrivateTableState);
                    if (data.state.state === 'started' && data.state.matchId) {
                        navigate(`/match/${data.state.matchId}`);
                    }
                }
```

Replace with:

```tsx
                if (data.type === 'lobby_update' && data.room === roomId && data.state) {
                    setTableState(data.state as PrivateTableState);
                    if (!leftMarker && data.state.state === 'started' && data.state.matchId) {
                        navigate(`/match/${data.state.matchId}`);
                    }
                }
```

Then add `leftMarker` to that effect's dependency array. Find:

```tsx
        socket.addEventListener('message', handle);
        return () => socket.removeEventListener('message', handle);
    }, [socket, isConnected, roomId, navigate]);
```

Replace with:

```tsx
        socket.addEventListener('message', handle);
        return () => socket.removeEventListener('message', handle);
    }, [socket, isConnected, roomId, navigate, leftMarker]);
```

- [ ] **Step 5: Clear the marker when the match is no longer active, and define the rejoin action**

After the effect added in Step 2, add an effect that drops the marker once the room reports the match is no longer running, plus the rejoin handler. Place this after the `fetchTableState` effect (`Table.tsx:72`):

```tsx
    // If the match ended (or the room is back to configuring) while we were
    // away, drop the marker so the normal room screen shows instead of Rejoin.
    useEffect(() => {
        if (leftMarker && tableState && tableState.state !== 'started') {
            clearLeftMatchMarker();
            setLeftMarker(null);
        }
    }, [leftMarker, tableState]);

    const handleRejoin = useCallback(() => {
        const session = loadPrivateRoomSession(roomId);
        const matchId = leftMarker?.matchId || (tableState as any)?.matchId;
        clearLeftMatchMarker();
        setLeftMarker(null);
        if (session?.token) connect(session.token);
        if (matchId) navigate(`/match/${matchId}`);
    }, [connect, navigate, roomId, leftMarker, tableState]);

    const copyRejoinLink = useCallback(async () => {
        const token = loadPrivateRoomSession(roomId)?.token;
        if (!token || !roomId || typeof window === 'undefined') return;
        const link = buildRejoinLink(window.location.origin, roomId, token);
        try {
            await navigator.clipboard.writeText(link);
        } catch {
            window.prompt('Copy your rejoin link:', link);
        }
    }, [roomId]);
```

- [ ] **Step 6: Render the Rejoin banner**

The banner must show even before the seat-screen guard. Find the start of the main returned JSX (`Table.tsx:310-313`):

```tsx
    return (
        <Page>
            <Shell wide>
                <Card>
```

Replace with:

```tsx
    return (
        <Page>
            <Shell wide>
                {leftMarker && (
                    <Card>
                        <Section
                            title="Match in progress"
                            subtitle="A bot is playing your seat while you're away."
                        >
                            <ToolsRow>
                                <Button variant="primary" onClick={handleRejoin}>Rejoin</Button>
                                <Button variant="default" onClick={copyRejoinLink}>Copy rejoin link</Button>
                            </ToolsRow>
                        </Section>
                    </Card>
                )}
                <Card>
```

Note: the early-return guest-login branch (`Table.tsx:274`, `if (!guestToken) { return ... }`) runs before this and is unaffected — a player who left has a saved token, so `guestToken` is set and this main branch renders.

- [ ] **Step 7: Verify it type-checks**

Run: `cd web && npx tsc --noEmit`
Expected: PASS — no type errors. (`useCallback` is already imported in `Table.tsx`.)

- [ ] **Step 8: Run the full web test + build**

Run: `cd web && npx vitest run && npx tsc --noEmit`
Expected: PASS — existing tests plus `rejoinMatch.test.ts` all green; no type errors.

- [ ] **Step 9: Commit**

```bash
git add web/src/pages/Table.tsx
git commit -m "feat(web): rejoin banner, cross-device link, suppress auto-rejoin while away"
```

---

## Task 5: End-to-end verification in the preview

**Files:** none (manual verification of the assembled flow).

- [ ] **Step 1: Start the stack**

Start the Go server and the web dev server per the README (`go run ./cmd/server`, then `cd web && npm run dev`). Use the preview tooling to drive the browser.

- [ ] **Step 2: Drive the exit → bot → rejoin loop**

1. Create a private room, fill the other three seats with bots, and start the match.
2. On the game table, confirm the **Exit** button is pinned to the top-right corner at a fixed size (it should not scale with the board).
3. Click **Exit** → confirm the modal appears. Click **Cancel** → modal closes, still in the match.
4. Click **Exit** again → **Leave**. Verify you land on `/room/:roomId` showing the **Match in progress** banner with **Rejoin** and **Copy rejoin link**, and that you are NOT bounced back into the match.
5. Watch the server logs: your seat should now be played automatically (`isAutomatedSeat` true once your socket closed).
6. Click **Rejoin** → verify you return to `/match/:matchId`, your seat is reclaimed (server logs: "reconnected to active room"), and the board state is current.

- [ ] **Step 3: Verify the cross-device link**

1. Leave the match again, click **Copy rejoin link**, and read the copied URL (it should be `…/room/<roomId>?token=<jwt>`).
2. Open that URL in a fresh browser context (or incognito). Verify it lands on the room with the **Rejoin** banner, the `?token=` param is stripped from the address bar, and clicking **Rejoin** enters the match and reclaims the seat.

- [ ] **Step 4: Verify match-end cleanup**

Leave a match and let the bots finish it (or end it). Confirm the **Match in progress** banner disappears and the normal room screen returns once the room is no longer in the `started` state.

- [ ] **Step 5: Capture proof**

Use a preview screenshot of the game table showing the Exit button and a screenshot of the Rejoin banner, and paste the relevant server log lines showing the seat handoff and reconnect.

---

## Self-Review

**Spec coverage:**
- Exit button top-right of game table → Task 2 (`ExitMatchButton`) + Task 3 (wiring). ✓
- Confirmation modal → Task 2. ✓
- Bot takes over on leave → no code (server `isAutomatedSeat`); leave closes the socket (Task 3 `handleLeaveMatch`). ✓
- Returns to waiting room → Task 3 `navigate('/room/:roomId')`. ✓
- `left-match` marker stops auto-bounce → Task 1 (helpers) + Task 4 Steps 3–4. ✓
- Rejoin banner on room screen → Task 4 Step 6. ✓
- Rejoin reconnects + navigates → Task 4 Step 5 (`handleRejoin`). ✓
- Cross-device link (`?token=`) generation → Task 2 `copyLink` + Task 4 `copyRejoinLink`; consumption → Task 4 Step 2. ✓
- Marker cleared when match ends while away → Task 4 Step 5 cleanup effect. ✓
- Token expired on rejoin → existing `handleAuthFailure` path in `Table.tsx` is untouched and still fires on 401. ✓
- Out of scope (per-seat human/bot indicator; backend rejoin codes; round-result Exit button) → intentionally not implemented. ✓

**Placeholder scan:** No TBD/TODO/"handle edge cases" placeholders; every code step contains complete code. The one empty string is `matchId: ''` in the cross-device link path (Step 2), which is intentional — a fresh device does not yet know the match id, and `handleRejoin` falls back to `(tableState as any)?.matchId` from the fetched room state.

**Type consistency:** `LeftMatchMarker` `{ roomId, matchId }` is used identically across Tasks 1, 3, and 4. Helper names (`saveLeftMatchMarker`, `loadLeftMatchMarker`, `clearLeftMatchMarker`, `buildRejoinLink`, `extractRejoinToken`, `stripTokenFromUrl`) match between definition (Task 1) and call sites (Tasks 2–4). `ExitMatchButton` props `{ roomId, onConfirmLeave }` match between definition (Task 2) and use (Task 3).
