# web/src/features/auth/

> Authentication pages and the credentialed-fetch helpers. Routes: `/login`, `/account`.

## Key Files

- **authClient.ts** — Credentialed fetch/CSRF helpers, safe internal return-path validation (`safeReturnTo`), `authRequestInit`, and one-time cleanup of legacy JWT storage (`clearLegacyCredentials`, `stripLegacyTokenParameter`). Exports the `AuthUser`/`AuthPayload` types.
- **authRouteState.ts** — Shared route-state and optional-versus-required login presentation rules (`AuthRouteState`, `resolveAuthDialogMode`).
- **AuthTicket.tsx** — Shared sign-in/register ticket. Login accepts one username-or-email field; registration collects the unique friendly username, email, and password.
- **AuthDialog.tsx** — Focus-trapped bone-paper account popup. Optional background-location opens support close/Escape/backdrop dismissal and restore focus; protected/invitation continuations omit dismissal. Its material classes live in `theme/base.css`, not here.
- **Login.tsx** — Invitation-aware login overlay; validates `returnTo` and resumes protected routes automatically after authentication.
- **Account.tsx** — Edits the unique username/email and exposes explicit current-device logout.
- **authClient.test.ts** / **authRouteState.test.ts** / **AuthDialog.test.ts** — Unit coverage for the helpers and dialog behavior.

## Architecture Notes

- **The session token never touches browser storage.** API credentials live only in the server-set HttpOnly cookie; `contexts/AuthContext.tsx` owns the bootstrap and holds the CSRF token in memory.
- Optional login entry points preserve the current route in `backgroundLocation`. Required account, room-create, invitation, and expired-session continuations use direct non-dismissible `/login?returnTo=...` navigation instead.
- `safeReturnTo` exists to stop an attacker-supplied `returnTo` from becoming an open redirect — validate before navigating, never after.
