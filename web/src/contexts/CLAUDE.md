# web/src/contexts/

> Global providers, nested `AuthProvider → SocketProvider → GameProvider`.

- **AuthContext.tsx** — loads `GET /api/v1/auth/session`, keeps the user and CSRF token in memory,
  and exposes `apiFetch` (credentials + CSRF on mutations). Distinguishes `401` from an offline
  bootstrap; logout revokes only the current session.
- **SocketContext.tsx** — `useSocket()`; opens `/api/v1/ws` with no query credentials (the browser
  sends the cookie), reconnects, and sends/receives binary protobuf. `disconnect(code?, reason?)`
  clears socket state synchronously; close code `4000` is the explicit leave-match signal.
- **GameContext.tsx** — `useGameState()`; decodes each frame with `game.GameState.decode()`,
  tracks `mySeatId`, and exposes `clearGameState()` so an intentional exit is not redirected back
  by a stale `matchId`.

Updates are not debounced: every broadcast re-renders.
