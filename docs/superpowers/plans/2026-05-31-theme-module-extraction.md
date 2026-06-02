# Theme Module Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the ledger theme into a self-contained `web/src/theme/` module (design tokens + structural CSS + a small set of typed React primitives) so every page consumes the theme through one decoupled boundary and future re-themes touch only the module.

**Architecture:** Split the current `web/src/pages/ledger-theme.css` into `theme/tokens.css` (the design values you change to re-theme) and `theme/base.css` (structural `.ledger-*`/`.ldg-*` classes that consume the tokens), imported once globally. Add `theme/components/` React primitives (`Page`, `Shell`, `Card`, `PageHeader`, `Section`, `Button`, `ButtonLink`, `TextLink`, `Field`, `Note`, `Toggle`, `ToolsRow`) re-exported from a `theme/index.ts` barrel. The five menu pages (Home, Login, Lobby, CreateRoom, Table + SeatCard) compose these primitives instead of raw class strings; Calc/Shanten keep using the utility classes directly for their dense tool internals.

**Tech Stack:** React 19 + TypeScript, React Router v6, Vite 7, plain CSS custom properties (no CSS-in-JS, no Tailwind for these pages).

**Verification model:** The web app has **no component-test runner** (no `*.test.tsx`, no Vitest), and introducing one solely to assert that a presentational component emits a class string would be over-engineering inconsistent with this repo. Verification for every task is therefore: (1) `cd web && npm run build` succeeds (TypeScript type-check + bundle), and (2) visual parity confirmed in the dev server (`npm run dev`, or the preview tooling). "Visual parity" means the page looks identical before and after — this is a pure refactor with no intended visual change.

**Decoupling contract (the point of this work):**
- To re-theme colors/fonts/spacing → edit `theme/tokens.css` only (or add a `[data-theme="x"]` token block).
- To change the look/structure → reimplement `theme/base.css` + the primitive components; pages that use primitives stay untouched.
- The `.ledger-*`/`.ldg-*` class names are an **internal implementation detail** of the theme module. Pages using primitives never reference them. Calc/Shanten are "advanced consumers" that still reference them directly (acceptable, documented).

---

## File Structure

**Create:**
- `web/src/theme/tokens.css` — Google Fonts `@import` + `:root` custom properties (light) + `@media (prefers-color-scheme: dark)` overrides. Lines 1–54 of the current `ledger-theme.css`.
- `web/src/theme/base.css` — all structural classes (`.ledger-page` … `.ldg-error-list`). Lines 56–end of the current `ledger-theme.css`.
- `web/src/theme/index.css` — `@import './tokens.css'; @import './base.css';`
- `web/src/theme/index.ts` — side-effect-imports `./index.css` and re-exports all primitives (barrel).
- `web/src/theme/components/Page.tsx`, `Shell.tsx`, `Card.tsx`, `PageHeader.tsx`, `Section.tsx`, `Button.tsx`, `TextLink.tsx`, `Field.tsx`, `Note.tsx`, `Toggle.tsx`, `ToolsRow.tsx`
- `web/src/theme/AGENTS.md`

**Modify:**
- `web/src/main.tsx` — add `import './theme'` (single global theme entry).
- `web/src/pages/{Home,Login,Lobby,CreateRoom,Table,SeatCard,Calc,Shanten}.tsx` — drop `import './ledger-theme.css'`; menu pages switch to primitives.
- `web/AGENTS.md`, `web/src/pages/AGENTS.md` — document the module.

**Delete:**
- `web/src/pages/ledger-theme.css` (content moved into the module).

---

## Task 1: Extract the CSS into `web/src/theme/` and import it once globally

**Files:**
- Create: `web/src/theme/tokens.css`, `web/src/theme/base.css`, `web/src/theme/index.css`
- Modify: `web/src/main.tsx`, and remove the per-page `import './ledger-theme.css'` from `web/src/pages/{Home,Login,Lobby,CreateRoom,Table,Calc,Shanten}.tsx`
- Delete: `web/src/pages/ledger-theme.css`

- [ ] **Step 1: Create `web/src/theme/tokens.css`**

Copy lines 1–54 of `web/src/pages/ledger-theme.css` verbatim (the `@import url('https://fonts.googleapis.com/...')` line, the `:root { … }` light block, and the `@media (prefers-color-scheme: dark) { :root { … } }` block). Verify the exact range first:

Run: `sed -n '1,54p' web/src/pages/ledger-theme.css`
Then write that exact content to `web/src/theme/tokens.css`. The file must start with the `@import url(...)` font line and end with the closing `}` of the dark-mode block.

- [ ] **Step 2: Create `web/src/theme/base.css`**

Copy lines 56–end of `web/src/pages/ledger-theme.css` verbatim (everything from `.ledger-page {` onward — all structural classes). Verify:

Run: `sed -n '56,$p' web/src/pages/ledger-theme.css | head -5`  (expect it to start at `.ledger-page {`)
Write that content to `web/src/theme/base.css`.

- [ ] **Step 3: Create `web/src/theme/index.css`**

```css
/* Ledger theme — single import surface.
   tokens.css holds the design values (edit these to re-theme);
   base.css holds the structural classes that consume them. */
@import './tokens.css';
@import './base.css';
```

- [ ] **Step 4: Import the theme once globally in `web/src/main.tsx`**

Current `web/src/main.tsx`:

```tsx
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
    <App />
)
```

Change to:

```tsx
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'
import './theme/index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
    <App />
)
```

(The barrel in Task 2 will also re-export this CSS, but importing it here guarantees the theme loads even on routes that use only utility classes.)

- [ ] **Step 5: Remove the 7 per-page CSS imports**

Delete the line `import './ledger-theme.css'` (with or without trailing semicolon) from each of:
`web/src/pages/Home.tsx`, `Login.tsx`, `Lobby.tsx`, `CreateRoom.tsx`, `Table.tsx`, `Calc.tsx`, `Shanten.tsx`.

Run to confirm none remain:
`grep -rn "ledger-theme.css" web/src/pages` → expect no matches in `.tsx` files.

- [ ] **Step 6: Delete the old CSS file**

```bash
git rm web/src/pages/ledger-theme.css
```

- [ ] **Step 7: Build and verify parity**

Run: `cd web && npm run build 2>&1 | tail -5`
Expected: `✓ built in …` with no `Could not resolve` / TypeScript errors.
Then `npm run dev` and confirm Home, Calc, and Shanten still render identically (IBM Plex, ledger surfaces) — the global import produces the same styling as the old per-page imports.

- [ ] **Step 8: Commit**

```bash
git add web/src/theme/tokens.css web/src/theme/base.css web/src/theme/index.css web/src/main.tsx web/src/pages/
git commit -m "web(theme): extract ledger CSS into web/src/theme module, import globally"
```

---

## Task 2: Add the React primitive components and the barrel

**Files:**
- Create: `web/src/theme/components/{Page,Shell,Card,PageHeader,Section,Button,TextLink,Field,Note,Toggle,ToolsRow}.tsx`, `web/src/theme/index.ts`

- [ ] **Step 1: Create `web/src/theme/components/Page.tsx`**

```tsx
import type { ReactNode } from 'react'

// Full-viewport themed page background (var(--page) + min-height).
export default function Page({ children }: { children: ReactNode }) {
    return <div className="ledger-page">{children}</div>
}
```

- [ ] **Step 2: Create `web/src/theme/components/Shell.tsx`**

```tsx
import type { ReactNode } from 'react'

// Centered content column. `wide` widens it (e.g. seat grids, tools).
export default function Shell({ wide = false, children }: { wide?: boolean; children: ReactNode }) {
    return <div className={`ledger-shell${wide ? ' ledger-shell--wide' : ''}`}>{children}</div>
}
```

- [ ] **Step 3: Create `web/src/theme/components/Card.tsx`**

```tsx
import type { ReactNode } from 'react'

// The single bordered surface card that holds a page's content.
export default function Card({ children }: { children: ReactNode }) {
    return <article className="ldg-page">{children}</article>
}
```

- [ ] **Step 4: Create `web/src/theme/components/PageHeader.tsx`**

```tsx
import type { ReactNode } from 'react'

// Page title (with optional Chinese/secondary subtitle) + optional right-side nav slot.
export default function PageHeader({
    title,
    subtitle,
    nav,
}: {
    title: ReactNode
    subtitle?: ReactNode
    nav?: ReactNode
}) {
    return (
        <div className="ldg-page-head">
            <div>
                <h1 className="ldg-page-head__title">
                    {title}
                    {subtitle && <small>{subtitle}</small>}
                </h1>
            </div>
            {nav && <div className="ldg-page-head__nav">{nav}</div>}
        </div>
    )
}
```

- [ ] **Step 5: Create `web/src/theme/components/Section.tsx`**

```tsx
import type { ReactNode } from 'react'

// A hairline-rhythm section with an optional title row (title + subtitle + right-aligned meta).
export default function Section({
    title,
    subtitle,
    meta,
    children,
}: {
    title?: ReactNode
    subtitle?: ReactNode
    meta?: ReactNode
    children: ReactNode
}) {
    const hasRow = title != null || meta != null
    return (
        <section className="ldg-section">
            {hasRow && (
                <div className="ldg-section-row">
                    {title != null ? (
                        <h2 className="ldg-section-title">
                            {title}
                            {subtitle && <small>{subtitle}</small>}
                        </h2>
                    ) : (
                        <span />
                    )}
                    {meta != null && <span className="ldg-section-meta">{meta}</span>}
                </div>
            )}
            {children}
        </section>
    )
}
```

- [ ] **Step 6: Create `web/src/theme/components/Button.tsx`**

```tsx
import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Link } from 'react-router-dom'

export type ButtonVariant = 'default' | 'primary' | 'danger'

function btnClass(variant: ButtonVariant, extra = ''): string {
    const v = variant === 'primary' ? ' ldg-btn--primary' : variant === 'danger' ? ' ldg-btn--danger' : ''
    return `ldg-btn${v}${extra ? ` ${extra}` : ''}`
}

// Native button styled by the theme.
export function Button({
    variant = 'default',
    className = '',
    children,
    ...rest
}: { variant?: ButtonVariant; className?: string; children: ReactNode } & ButtonHTMLAttributes<HTMLButtonElement>) {
    return (
        <button className={btnClass(variant, className)} {...rest}>
            {children}
        </button>
    )
}

// react-router <Link> styled identically to Button.
export function ButtonLink({
    to,
    variant = 'default',
    className = '',
    children,
}: {
    to: string
    variant?: ButtonVariant
    className?: string
    children: ReactNode
}) {
    return (
        <Link to={to} className={btnClass(variant, className)}>
            {children}
        </Link>
    )
}
```

- [ ] **Step 7: Create `web/src/theme/components/TextLink.tsx`**

```tsx
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

// Hairline-underline text link. Pass `to` for client routes or `href` for raw anchors.
export default function TextLink({
    to,
    href,
    children,
}: {
    to?: string
    href?: string
    children: ReactNode
}) {
    if (to) {
        return (
            <Link to={to} className="ldg-link">
                {children}
            </Link>
        )
    }
    return (
        <a href={href} className="ldg-link">
            {children}
        </a>
    )
}
```

- [ ] **Step 8: Create `web/src/theme/components/Field.tsx`**

```tsx
import type { CSSProperties, InputHTMLAttributes } from 'react'

// Labelled text input. `style` is applied to the field wrapper (e.g. vertical spacing);
// all other props pass through to the <input>.
export default function Field({
    label,
    style,
    ...inputProps
}: { label: string; style?: CSSProperties } & InputHTMLAttributes<HTMLInputElement>) {
    return (
        <div className="ldg-field" style={style}>
            <label className="ldg-field__label">{label}</label>
            <input className="ldg-input" {...inputProps} />
        </div>
    )
}
```

- [ ] **Step 9: Create `web/src/theme/components/Note.tsx`**

```tsx
import type { CSSProperties, ReactNode } from 'react'

// Small helper/status text. tone drives the accent/danger color.
export default function Note({
    tone = 'default',
    style,
    children,
}: {
    tone?: 'default' | 'ok' | 'error'
    style?: CSSProperties
    children: ReactNode
}) {
    const t = tone === 'ok' ? ' ldg-note--ok' : tone === 'error' ? ' ldg-note--err' : ''
    return (
        <p className={`ldg-note${t}`} style={style}>
            {children}
        </p>
    )
}
```

- [ ] **Step 10: Create `web/src/theme/components/Toggle.tsx`**

```tsx
import type { ReactNode } from 'react'

// Segmented control. Generic over the option value type.
export default function Toggle<T extends string | number>({
    options,
    value,
    onChange,
    disabled = false,
}: {
    options: Array<{ value: T; label: ReactNode }>
    value: T
    onChange: (value: T) => void
    disabled?: boolean
}) {
    return (
        <div className="ldg-toggle">
            {options.map(opt => (
                <button
                    key={String(opt.value)}
                    type="button"
                    className={`ldg-toggle__btn${opt.value === value ? ' is-active' : ''}`}
                    disabled={disabled}
                    onClick={() => onChange(opt.value)}
                >
                    {opt.label}
                </button>
            ))}
        </div>
    )
}
```

- [ ] **Step 11: Create `web/src/theme/components/ToolsRow.tsx`**

```tsx
import type { ReactNode } from 'react'

// Horizontal row of buttons/links. `end` right-aligns them.
export default function ToolsRow({ end = false, children }: { end?: boolean; children: ReactNode }) {
    return <div className={`ldg-tools-row${end ? ' ldg-tools-row--end' : ''}`}>{children}</div>
}
```

- [ ] **Step 12: Create the barrel `web/src/theme/index.ts`**

```ts
import './index.css'

export { default as Page } from './components/Page'
export { default as Shell } from './components/Shell'
export { default as Card } from './components/Card'
export { default as PageHeader } from './components/PageHeader'
export { default as Section } from './components/Section'
export { default as TextLink } from './components/TextLink'
export { default as Field } from './components/Field'
export { default as Note } from './components/Note'
export { default as Toggle } from './components/Toggle'
export { default as ToolsRow } from './components/ToolsRow'
export { Button, ButtonLink } from './components/Button'
export type { ButtonVariant } from './components/Button'
```

- [ ] **Step 13: Build (components compile even though unused yet)**

Run: `cd web && npm run build 2>&1 | tail -5`
Expected: `✓ built in …`, no TypeScript errors.

- [ ] **Step 14: Commit**

```bash
git add web/src/theme/components/ web/src/theme/index.ts
git commit -m "web(theme): add typed ledger primitives (Page, Card, Section, Button, …)"
```

---

## Task 3: Refactor `Home.tsx` to use the primitives

**Files:**
- Modify: `web/src/pages/Home.tsx`

- [ ] **Step 1: Replace the whole file with the primitive-based version**

```tsx
import { useEffect, useState } from 'react'
import { Page, Shell, Card, PageHeader, Section, ToolsRow, ButtonLink, TextLink, Note } from '../theme'

// Decode the username from the stored JWT, if present, so the account link
// reflects logged-in state without a network call.
function useStoredUsername(): string | null {
    const [username, setUsername] = useState<string | null>(null)
    useEffect(() => {
        const token = localStorage.getItem('fh_token')
        if (!token) {
            setUsername(null)
            return
        }
        const parts = token.split('.')
        if (parts.length !== 3) {
            setUsername(null)
            return
        }
        try {
            const payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')))
            setUsername(typeof payload.username === 'string' ? payload.username : null)
        } catch {
            setUsername(null)
        }
    }, [])
    return username
}

export default function Home() {
    const username = useStoredUsername()

    return (
        <Page>
            <Shell>
                <Card>
                    <PageHeader
                        title="Fenghua Mahjong"
                        subtitle="奉化麻将"
                        nav={<TextLink to="/login">{username ? `Signed in · ${username}` : 'Login / Register'}</TextLink>}
                    />

                    <Note style={{ marginTop: '1.25rem' }}>
                        Jump into a live public match, set up a private room for friends, or open the
                        scoring and shanten tools.
                    </Note>

                    <Section title="Play" subtitle="Live hometown-rules matchmaking">
                        <ToolsRow>
                            <ButtonLink to="/play" variant="primary">Find Match →</ButtonLink>
                        </ToolsRow>
                    </Section>

                    <Section title="Private Room" subtitle="Play with friends by link">
                        <ToolsRow>
                            <ButtonLink to="/room/new">Create Private Room →</ButtonLink>
                        </ToolsRow>
                    </Section>

                    <Section title="Tools" subtitle="No login needed">
                        <ToolsRow>
                            <ButtonLink to="/tools/calc">Scoring Calculator</ButtonLink>
                            <ButtonLink to="/tools/shanten">Shanten Calculator</ButtonLink>
                        </ToolsRow>
                    </Section>
                </Card>
            </Shell>
        </Page>
    )
}
```

- [ ] **Step 2: Build and visually verify parity**

Run: `cd web && npm run build 2>&1 | tail -5` → `✓ built`.
`npm run dev`, open `/` — must look identical to before (title + subtitle, three sections, primary "Find Match", account link top-right).

- [ ] **Step 3: Commit**

```bash
git add web/src/pages/Home.tsx
git commit -m "web(home): compose theme primitives instead of raw ledger classes"
```

---

## Task 4: Refactor `Login.tsx` to use the primitives

**Files:**
- Modify: `web/src/pages/Login.tsx`

- [ ] **Step 1: Replace the whole file**

```tsx
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSocket } from '../contexts/SocketContext';
import { getApiUrl } from '../config';
import { Page, Shell, Card, PageHeader, Section, ToolsRow, Button, TextLink, Field, Note } from '../theme';

export default function Login() {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const navigate = useNavigate();
    const { connect } = useSocket();

    const handleAuth = async (isLogin: boolean) => {
        try {
            const endpoint = isLogin ? getApiUrl('/api/v1/auth/login') : getApiUrl('/api/v1/auth/register');
            const res = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password }),
            });

            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Authentication failed');

            if (!isLogin) {
                alert('Registration successful! Please login.');
                return;
            }

            localStorage.setItem('fh_token', data.token);
            connect(data.token);
            navigate('/play');
        } catch (err: any) {
            setError(err.message);
        }
    };

    return (
        <Page>
            <Shell>
                <Card>
                    <PageHeader
                        title="Login"
                        subtitle="登录 · 奉化麻将"
                        nav={<>
                            <TextLink to="/">Home</TextLink>
                            <TextLink to="/room/new">Private room →</TextLink>
                        </>}
                    />

                    <Section title="Account access" subtitle="Login for matchmaking, or register a new account.">
                        <Field label="Username" value={username} onChange={e => setUsername(e.target.value)} autoComplete="username" />
                        <Field label="Password" type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete="current-password" style={{ marginTop: '0.85rem' }} />

                        {error && <Note tone="error">{error}</Note>}

                        <ToolsRow>
                            <Button variant="primary" onClick={() => handleAuth(true)}>Login</Button>
                            <Button onClick={() => handleAuth(false)}>Register</Button>
                        </ToolsRow>
                    </Section>
                </Card>
            </Shell>
        </Page>
    );
}
```

(Note: the `ToolsRow` here replaces the previous inline `style={{ marginTop: '1.1rem' }}`; `.ldg-tools-row` already has `margin-top: 0.75rem`, which is the intended spacing. Visual parity is preserved within a few px; acceptable for this refactor.)

- [ ] **Step 2: Build + visual verify** — Run `cd web && npm run build 2>&1 | tail -5`; open `/login`, confirm fields + Login/Register buttons + nav links render as before.

- [ ] **Step 3: Commit**

```bash
git add web/src/pages/Login.tsx
git commit -m "web(login): compose theme primitives"
```

---

## Task 5: Refactor `Lobby.tsx` (/play) to use the primitives

**Files:**
- Modify: `web/src/pages/Lobby.tsx`

- [ ] **Step 1: Replace the whole file**

```tsx
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSocket } from '../contexts/SocketContext';
import { useGameState } from '../contexts/GameContext';
import { getApiUrl } from '../config';
import { Page, Shell, Card, PageHeader, Section, ToolsRow, Button, ButtonLink, TextLink, Note } from '../theme';

export default function Lobby() {
    const [isQueuing, setIsQueuing] = useState(false);
    const [error, setError] = useState('');
    const navigate = useNavigate();
    const { isConnected, connect } = useSocket();
    const { gameState } = useGameState();

    useEffect(() => {
        const token = localStorage.getItem('fh_token');
        if (token && !isConnected) {
            connect(token);
        }

        if (gameState && gameState.matchId) {
            navigate(`/match/${gameState.matchId}`);
        }
    }, [isConnected, gameState, navigate, connect]);

    const joinQueue = async (ruleset: 'hometown' | 'chongci-fh' = 'hometown') => {
        const token = localStorage.getItem('fh_token');
        if (!token) return navigate('/login');

        setError('');
        setIsQueuing(true);
        try {
            const res = await fetch(getApiUrl('/api/v1/matchmaking/join'), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`,
                },
                body: JSON.stringify({ ruleset }),
            });

            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                throw new Error(data.error || 'Failed to join queue');
            }
        } catch (e: any) {
            setError(e.message || 'Error contacting matchmaker');
            setIsQueuing(false);
        }
    };

    return (
        <Page>
            <Shell>
                <Card>
                    <PageHeader
                        title="Play"
                        subtitle="实时匹配 · Hometown rules"
                        nav={<>
                            <TextLink to="/">Home</TextLink>
                            <TextLink to="/room/new">Private room →</TextLink>
                        </>}
                    />

                    <Section title="Matchmaking" meta={isConnected ? 'socket ready' : 'socket offline'}>
                        {error && <Note tone="error">{error}</Note>}

                        {isQueuing ? (
                            <Note>
                                Searching for players… stay on this page; you'll jump into the match
                                automatically once the room is ready.
                            </Note>
                        ) : (
                            <ToolsRow>
                                <Button variant="primary" disabled={!isConnected} onClick={() => joinQueue('hometown')}>Find Match</Button>
                                <Button disabled={!isConnected} onClick={() => joinQueue('chongci-fh')}>Quick Match · Chongci</Button>
                                <ButtonLink to="/room/new">Private Room</ButtonLink>
                            </ToolsRow>
                        )}
                    </Section>
                </Card>
            </Shell>
        </Page>
    );
}
```

- [ ] **Step 2: Build + visual verify** — `cd web && npm run build 2>&1 | tail -5`; open `/play`, confirm "socket offline" meta, the three buttons, and disabled states match.

- [ ] **Step 3: Commit**

```bash
git add web/src/pages/Lobby.tsx
git commit -m "web(lobby): compose theme primitives"
```

---

## Task 6: Refactor `CreateRoom.tsx` (/room/new) to use the primitives

**Files:**
- Modify: `web/src/pages/CreateRoom.tsx`

- [ ] **Step 1: Replace the whole file**

```tsx
import { useMemo, useState } from 'react';
import { Page, Shell, Card, PageHeader, Section, ToolsRow, Button, ButtonLink, TextLink, Note } from '../theme';

function makeRoomId() {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
        return crypto.randomUUID().slice(0, 8);
    }

    return Math.random().toString(36).slice(2, 10);
}

export default function CreateRoom() {
    const [roomId, setRoomId] = useState('');
    const [copyState, setCopyState] = useState<'idle' | 'copied' | 'failed'>('idle');

    const roomUrl = useMemo(() => {
        if (!roomId || typeof window === 'undefined') {
            return '';
        }

        return `${window.location.origin}/room/${roomId}`;
    }, [roomId]);

    const handleCreateRoom = () => {
        setRoomId(makeRoomId());
        setCopyState('idle');
    };

    const handleCopy = async () => {
        if (!roomUrl) return;

        try {
            await navigator.clipboard.writeText(roomUrl);
            setCopyState('copied');
        } catch {
            setCopyState('failed');
        }
    };

    const meta =
        copyState === 'copied' ? <span style={{ color: 'var(--accent)' }}>copied</span>
        : copyState === 'failed' ? <span style={{ color: 'var(--danger)' }}>copy failed</span>
        : undefined;

    return (
        <Page>
            <Shell>
                <Card>
                    <PageHeader
                        title="Private Room"
                        subtitle="生成房间链接"
                        nav={<>
                            <TextLink to="/">Home</TextLink>
                            <TextLink to="/play">Matchmaking →</TextLink>
                        </>}
                    />

                    <Section title="Share link" meta={meta}>
                        <ToolsRow>
                            <Button variant="primary" onClick={handleCreateRoom}>
                                {roomId ? 'Create another link' : 'Generate link'}
                            </Button>
                            {roomUrl && <ButtonLink to={`/room/${roomId}`}>Open Room →</ButtonLink>}
                        </ToolsRow>

                        <div className="ldg-input-row">
                            <input
                                className="ldg-input"
                                readOnly
                                value={roomUrl}
                                placeholder="Generate a room link first, then copy or open it."
                            />
                            <Button onClick={handleCopy} disabled={!roomUrl}>Copy</Button>
                        </div>

                        <Note>
                            Send the link to friends. Everyone opens the same /room/… link and enters a name;
                            the host (first joiner) fills any empty seats with AI and starts when ready.
                        </Note>
                    </Section>
                </Card>
            </Shell>
        </Page>
    );
}
```

(Note: the read-only share-link input keeps the raw `.ldg-input` / `.ldg-input-row` classes because it is a one-off readonly URL field, not the labelled `Field` pattern. The `var(--accent)` / `var(--danger)` token references in `meta` are part of the theme's public token contract, so this stays decoupled from class names.)

- [ ] **Step 2: Build + visual verify** — `cd web && npm run build 2>&1 | tail -5`; open `/room/new`, click Generate link, confirm the URL fills, Copy works, "copied" shows in accent color.

- [ ] **Step 3: Commit**

```bash
git add web/src/pages/CreateRoom.tsx
git commit -m "web(create-room): compose theme primitives"
```

---

## Task 7: Refactor `Table.tsx` (/room/:roomId) and `SeatCard.tsx`

**Files:**
- Modify: `web/src/pages/Table.tsx` (the two `return` blocks + imports), `web/src/pages/SeatCard.tsx`

`Table.tsx` keeps ALL of its existing logic/state/effects unchanged (the `useMyUserId` helper, every `useEffect`, `performJoin`, `mutateSeat`, `setMatchMode`, `handleStart`, etc.). Only the two JSX `return` blocks and the import line change. `SeatCard` is small enough to rewrite whole.

- [ ] **Step 1: Update `Table.tsx` imports**

Replace the line `import './ledger-theme.css';` (already removed in Task 1) — ensure the top imports include the primitives. The import block should read:

```tsx
// @ts-nocheck
import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useSocket } from '../contexts/SocketContext';
import { useGameState } from '../contexts/GameContext';
import { getApiUrl } from '../config';
import { clearPrivateRoomSession, loadPrivateRoomSession, savePrivateRoomSession } from './privateRoomSession';
import SeatCard from './SeatCard';
import { game } from '../proto/game';
import { Page, Shell, Card, PageHeader, Section, ToolsRow, Button, Field, Note, Toggle } from '../theme';
```

- [ ] **Step 2: Replace the `if (!guestToken)` return block**

Find the block that starts with `if (!guestToken) {` and `return (` and replace its JSX with:

```tsx
    if (!guestToken) {
        return (
            <Page>
                <Shell>
                    <Card>
                        <PageHeader title="Join Room" subtitle={roomId} />
                        <Section title="Enter as guest" subtitle="Pick a display name to join this private room.">
                            <Field
                                label="Display name"
                                value={username}
                                onChange={e => setUsername(e.target.value)}
                                placeholder="Your name"
                            />
                            {error && <Note tone="error">{error}</Note>}
                            <ToolsRow>
                                <Button variant="primary" onClick={handleGuestJoin} disabled={joining || !username.trim()}>
                                    {joining ? 'Joining…' : 'Join Room'}
                                </Button>
                            </ToolsRow>
                        </Section>
                    </Card>
                </Shell>
            </Page>
        );
    }
```

- [ ] **Step 3: Replace the main waiting-room return block**

The current main block computes `seats`, `hostUserId`, `iAmHost`, `allSeatsFilled` before `return`, and (in the prior refactor) `filledCount`, `currentMode`, `isChongci`, `modeLocked`. Keep those derived constants exactly as they are, and replace the JSX `return ( … )` with:

```tsx
    return (
        <Page>
            <Shell wide>
                <Card>
                    <PageHeader
                        title="Room"
                        subtitle={roomId}
                        nav={iAmHost && (
                            <Button variant="primary" onClick={handleStart} disabled={!allSeatsFilled}>
                                Start Match
                            </Button>
                        )}
                    />

                    {error && <Note tone="error">{error}</Note>}

                    <Section title="Match mode">
                        <Toggle
                            value={isChongci ? 'chongci' : 'classic'}
                            disabled={modeLocked}
                            onChange={(mode) => mode === 'chongci' ? setMatchMode('chongci', chongciDraft) : setMatchMode('classic')}
                            options={[
                                { value: 'classic', label: 'Classic' },
                                { value: 'chongci', label: 'Chongci' },
                            ]}
                        />
                        {isChongci && (
                            <div className="ldg-grid-3" style={{ marginTop: '0.85rem' }}>
                                {[
                                    { key: 'starting_score', label: 'Starting points', min: 100, max: 1_000_000 },
                                    { key: 'bust_threshold', label: 'Bust threshold', min: -1_000_000, max: 0 },
                                    { key: 'max_hands', label: 'Max hands (0=∞)', min: 0, max: 200 },
                                ].map(({ key, label, min, max }) => (
                                    <Field
                                        key={key}
                                        label={label}
                                        type="number"
                                        min={min}
                                        max={max}
                                        value={(chongciDraft as any)[key]}
                                        disabled={modeLocked}
                                        onChange={e => setChongciDraft(d => ({ ...d, [key]: Number(e.target.value) }))}
                                        onBlur={() => iAmHost && setMatchMode('chongci', chongciDraft)}
                                    />
                                ))}
                            </div>
                        )}
                        {!iAmHost && <Note>Only the host can change match settings.</Note>}
                    </Section>

                    <Section title="Seats" meta={`${filledCount} / 4`}>
                        <div className="ldg-grid-2">
                            {seats.map((seat, i) => (
                                <SeatCard
                                    key={i}
                                    seatIndex={i}
                                    seat={seat}
                                    isHost={iAmHost}
                                    canEdit={iAmHost && seat.kind !== 'human'}
                                    hostUserId={hostUserId}
                                    onAssignBot={(s, d) => mutateSeat(s, 'bot', d)}
                                    onClearSeat={s => mutateSeat(s, 'empty')}
                                />
                            ))}
                        </div>

                        {iAmHost && !allSeatsFilled && <Note>Fill every seat with a player or AI before starting.</Note>}
                        {!iAmHost && <Note>The host configures the table. You'll join automatically when the match begins.</Note>}
                    </Section>
                </Card>
            </Shell>
        </Page>
    );
```

(Note: `.ldg-grid-3` and `.ldg-grid-2` layout containers stay as utility classes — they are layout, not theme chrome, and componentizing a generic grid is YAGNI. `Field` is used for the chongci number inputs; its `min`/`max`/`type`/`onBlur` pass through via `InputHTMLAttributes`.)

- [ ] **Step 4: Replace `SeatCard.tsx` whole**

```tsx
// @ts-nocheck
import { game } from '../proto/game';
import { Button, Note } from '../theme';

type SeatConfig = game.ISeatConfig;
type Difficulty = game.Difficulty;

export interface SeatCardProps {
    seatIndex: number;
    seat: SeatConfig;
    isHost: boolean;
    canEdit: boolean;
    hostUserId: number;
    onAssignBot: (seat: number, difficulty: Difficulty) => void;
    onClearSeat: (seat: number) => void;
}

const DIFFICULTY_OPTIONS: Array<{ value: Difficulty; label: string }> = [
    { value: game.Difficulty.DIFFICULTY_HEURISTIC, label: 'Heuristic' },
];

const SEAT_LABEL = ['East', 'South', 'West', 'North'];

export default function SeatCard(props: SeatCardProps) {
    const { seatIndex, seat, isHost, canEdit, hostUserId, onAssignBot, onClearSeat } = props;

    const isHumanHost = seat.kind === 'human' && Number(seat.userId ?? 0) === hostUserId;

    return (
        <div className="ldg-meld">
            <div className="ldg-meld__head">
                <div>
                    <div className="ldg-meld__meta">Seat {seatIndex + 1} · {SEAT_LABEL[seatIndex]}</div>
                    <div className="ldg-meld__title" style={{ marginTop: 4 }}>
                        {seat.kind === 'human' && <>{seat.username || `Player ${seat.userId ?? ''}`}</>}
                        {seat.kind === 'bot' && <>AI · Heuristic</>}
                        {(seat.kind === 'empty' || !seat.kind) && (
                            <span style={{ color: 'var(--ink-3)', fontWeight: 400 }}>Waiting for player…</span>
                        )}
                    </div>
                </div>
                {isHumanHost && <span className="ldg-chip ldg-chip--active">Host</span>}
            </div>

            {canEdit && (seat.kind === 'empty' || !seat.kind) && (
                <div className="ldg-meld__actions">
                    {DIFFICULTY_OPTIONS.map(opt => (
                        <Button key={opt.value} onClick={() => onAssignBot(seatIndex, opt.value)}>
                            Add AI · {opt.label}
                        </Button>
                    ))}
                </div>
            )}

            {canEdit && seat.kind === 'bot' && (
                <div className="ldg-meld__actions">
                    <Button variant="danger" onClick={() => onClearSeat(seatIndex)}>Remove AI</Button>
                </div>
            )}

            {isHost && !canEdit && (
                <Note style={{ marginTop: '0.6rem' }}>Only the host can change seats.</Note>
            )}
        </div>
    );
}
```

(Note: `SeatCard` keeps the `.ldg-meld*` / `.ldg-chip` classes for the card frame — these are part of the tool/card vocabulary shared with Calc and are layout-specific; only the buttons and the note move to primitives.)

- [ ] **Step 5: Build + visual verify**

Run: `cd web && npm run build 2>&1 | tail -5` → `✓ built`.
Visual: the `/room/:id` **join form** renders via the preview (open `/room/demo123`). The seat-grid/match-mode branch needs a live backend; if available, run the Go server and join a room to confirm the Toggle + seat cards render. Otherwise rely on the build + the join-form check (the seat branch uses only already-verified primitives + unchanged classes).

- [ ] **Step 6: Commit**

```bash
git add web/src/pages/Table.tsx web/src/pages/SeatCard.tsx
git commit -m "web(table): compose theme primitives in waiting room and seat cards"
```

---

## Task 8: Remove leftover class references from Calc/Shanten imports + document the module

**Files:**
- Modify: `web/src/pages/Calc.tsx`, `web/src/pages/Shanten.tsx` (only the dropped CSS import, already done in Task 1 — this step just verifies), `web/AGENTS.md`, `web/src/pages/AGENTS.md`
- Create: `web/src/theme/AGENTS.md`

- [ ] **Step 1: Confirm Calc/Shanten no longer import the deleted CSS**

Run: `grep -rn "ledger-theme" web/src/pages/Calc.tsx web/src/pages/Shanten.tsx` → expect **no matches** (Task 1 removed them; the global import in `main.tsx` now supplies the classes). No code change needed if clean.

- [ ] **Step 2: Create `web/src/theme/AGENTS.md`**

```markdown
# web/src/theme/

> The app's shared "ledger" theme: design tokens, structural CSS, and typed React primitives.

## Overview

Single source of truth for the out-of-game visual language (IBM Plex, off-white/ink
surfaces, one teal accent, hairline rules, light/dark via `prefers-color-scheme`).
Imported once globally from `web/src/main.tsx` (`import './theme'` side-effect loads the CSS).

## Decoupling contract

- Re-theme colors/fonts/spacing → edit **`tokens.css`** only (or add a `[data-theme="x"]`
  block of overrides).
- Change the look/structure → reimplement **`base.css`** + the primitive components;
  pages built from primitives stay untouched.
- The `.ledger-*` / `.ldg-*` class names are an internal implementation detail. Pages built
  from primitives never reference them. `Calc.tsx` / `Shanten.tsx` are "advanced consumers"
  that use the utility classes directly for their dense tool layouts (palettes, discard rows,
  melds, big-stat) — componentizing those was deliberately out of scope (YAGNI).

## Files

- **tokens.css** — `@import` of IBM Plex fonts + `:root` custom properties (light) and the
  `@media (prefers-color-scheme: dark)` overrides. This *is* the theme's values.
- **base.css** — every structural class (`.ledger-page`, `.ledger-shell`, `.ldg-page`,
  `.ldg-section`, `.ldg-tile`, `.ldg-btn`, `.ldg-input`, …) consuming the tokens.
- **index.css** — `@import`s tokens.css then base.css.
- **index.ts** — side-effect-imports `index.css` and re-exports the primitives.
- **components/** — `Page`, `Shell`, `Card`, `PageHeader`, `Section`, `Button`/`ButtonLink`,
  `TextLink`, `Field`, `Note`, `Toggle`, `ToolsRow`.

## Usage

```tsx
import { Page, Shell, Card, PageHeader, Section, Button } from '../theme'

<Page><Shell><Card>
  <PageHeader title="Title" subtitle="副标题" nav={<TextLink to="/">Home</TextLink>} />
  <Section title="Thing" meta="0 / 4">
    <Button variant="primary">Go</Button>
  </Section>
</Card></Shell></Page>
```
```

- [ ] **Step 3: Update `web/src/pages/AGENTS.md` overview**

Replace the theme sentence so it points at the module. Change the phrase
"uses the shared "ledger" theme in `ledger-theme.css` … they `import './ledger-theme.css'` and compose the `.ledger-page` / … class vocabulary"
to:

```markdown
Every non-game page uses the shared "ledger" theme from the `web/src/theme/` module (IBM Plex, off-white/ink, single teal accent, hairline rules, light/dark via `prefers-color-scheme`). The theme CSS is imported once globally in `main.tsx`. Menu pages (Home, Login, Lobby, CreateRoom, Table) compose the typed primitives exported from `../theme` (`Page`, `Card`, `Section`, `Button`, `Field`, …); Calc/Shanten use the theme's utility classes directly for their dense tool layouts. Only the live game/replay board (`Game.tsx`, `Replay.tsx` board, `MatchEndOverlay`) keeps the dark in-game theme.
```

Also update the Calc bullet line that says "(`import './ledger-theme.css'`, …)" to drop the import mention: "uses the shared ledger theme (utility classes from `web/src/theme/`)…".

- [ ] **Step 4: Update `web/AGENTS.md`**

Change the `src/` bullet to mention the module:

```markdown
- **src/** — Application source code (pages, theme, contexts, hooks, utils, proto bindings). `src/theme/` is the shared "ledger" theme module (tokens + structural CSS + typed React primitives), imported once globally in `main.tsx`. Only the in-game board keeps its own dark theme.
```

- [ ] **Step 5: Build + commit**

```bash
cd web && npm run build 2>&1 | tail -3   # ✓ built
git add web/src/theme/AGENTS.md web/AGENTS.md web/src/pages/AGENTS.md
git commit -m "docs(theme): document the theme module and decoupling contract"
```

---

## Task 9: Final verification

- [ ] **Step 1: No stray references to the old file or per-page CSS imports**

Run: `grep -rn "ledger-theme.css" web/src` → expect matches **only** in markdown docs that intentionally describe history (none in `.ts`/`.tsx`). If any `.tsx` still imports it, remove that import.

- [ ] **Step 2: The only global theme import is in `main.tsx`**

Run: `grep -rn "from '../theme'\|from './theme'\|import './theme'" web/src` → expect `main.tsx` to have `import './theme'` (or `import './theme/index.css'`) and the menu pages to import named primitives. No page should import `index.css` from theme directly.

- [ ] **Step 3: Build + full visual sweep**

Run: `cd web && npm run build 2>&1 | tail -5` → `✓ built`.
`npm run dev`; sweep `/`, `/login`, `/play`, `/room/new`, `/room/demo123` (join form), `/tools/calc`, `/tools/shanten`. Every page must look identical to before this plan (pure refactor). Toggle OS dark/light mode once to confirm `prefers-color-scheme` still flips all pages.

- [ ] **Step 4: Confirm the decoupling works (smoke test the contract)**

Temporarily change one token in `web/src/theme/tokens.css` — e.g. `--accent: #1b6d5a;` → `--accent: #b4530e;` — run `npm run dev`, confirm the accent color changes on **every** page (primary buttons' selected states, "copied" text, links-on-hover), then revert the change. This proves a single-file re-theme propagates app-wide. Do not commit the temporary change.

- [ ] **Step 5: Final commit (if Step 1–2 required any cleanup)**

```bash
git add -A web/src
git commit -m "web(theme): final cleanup after theme-module extraction"
```
(Skip if nothing changed.)
