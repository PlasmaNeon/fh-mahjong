# web/

> The React single-page app: lobby, live table, replays and AI review, and rules tools.

Vite + React 19 + TypeScript, TailwindCSS 4, Framer Motion 12, protobufjs 8. Game state arrives
as binary protobuf over WebSocket.

## Layout

- **src/** — application source; see `src/CLAUDE.md`.
- **public/** — static assets: tile SVGs in `Regular_shortnames/` (I.Mahjong-HK artwork; license
  and attribution in `SOURCE.md` and `LICENSE.hk.txt`), plus `mahjong.wasm` / `wasm_exec.js`,
  which nothing loads.
- **dist/** — build output (`npm run build`), embedded into the Go binary by `embed.go`. CI uses
  the tracked stub files so no frontend build is needed for Go tests.
- **index.html** — the app entry; **ui-prototype.html** — a separate dev-only entry for the
  Direct play navigation prototype (`src/features/dev/DirectPlayPrototype.tsx`), not in the
  production build.
- **.env.example** — optional backend URLs (`VITE_API_BASE_URL`, `VITE_WS_BASE_URL`).

## Commands

```bash
npm run dev        # Vite on :3000, proxies /api and WebSocket to :8080
npm run build      # tsc && vite build → dist/
npx tsc            # CI type-check
npx vitest run     # CI tests (node environment, *.test.ts only)
```

While iterating on `localhost:3000`, rely on HMR; build only when asked, before deploy, or when a
change is type-risky.

## Deployment

- Preferred: the Go server serves `dist/` (single service), or a reverse proxy exposes `/api`
  and `/api/v1/ws` on the frontend's origin, so session cookies stay first-party.
- Split hosting (e.g. Vercel for the frontend) needs `VITE_API_BASE_URL` / `VITE_WS_BASE_URL`, a
  same-site backend listed in `FRONTEND_ORIGINS`, and a rewrite of client routes to `index.html`.
- Tile face URLs go through `getTileSvgUrl()`, which adds a version query because the Go server
  caches SVGs for 30 days; bump the version when replacing artwork.
- Regenerate `src/proto/game.js` and `game.d.ts` whenever `proto/game.proto` changes.
