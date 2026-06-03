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

type PrivateTableState = game.IPrivateTableState;
type Difficulty = game.Difficulty;

export default function Table() {
    const { roomId } = useParams();
    const [username, setUsername] = useState(() => loadPrivateRoomSession(roomId)?.username ?? '');
    const [guestToken, setGuestToken] = useState('');
    const [joining, setJoining] = useState(false);
    const [starting, setStarting] = useState(false);
    const [error, setError] = useState('');
    const [tableState, setTableState] = useState<PrivateTableState | null>(null);
    const [chongciDraft, setChongciDraft] = useState({ starting_score: 2000, bust_threshold: 0, max_hands: 50 });
    const [rlAgentAvailable, setRlAgentAvailable] = useState(false);

    const navigate = useNavigate();
    const { isConnected, connect, socket } = useSocket();
    const { gameState } = useGameState();

    const myUserId = useMyUserId(guestToken);

    useEffect(() => {
        if (gameState && gameState.matchId) {
            navigate(`/match/${gameState.matchId}`);
        }
    }, [gameState, navigate]);

    useEffect(() => {
        const stored = loadPrivateRoomSession(roomId);
        if (stored && !isConnected) {
            setGuestToken(stored.token);
            setUsername(stored.username);
            connect(stored.token);
        }
    }, [connect, isConnected, roomId]);

    const handleAuthFailure = useCallback(() => {
        clearPrivateRoomSession(roomId);
        setGuestToken('');
        setTableState(null);
        setError('Your private room session expired. Enter your name again.');
    }, [roomId]);

    const fetchTableState = useCallback(async () => {
        if (!roomId || !guestToken) return;
        try {
            const res = await fetch(getApiUrl(`/api/v1/rooms/${roomId}`), {
                headers: { Authorization: `Bearer ${guestToken}` },
            });
            if (res.status === 401) {
                handleAuthFailure();
                return;
            }
            if (res.ok) {
                setTableState(await res.json());
            }
        } catch (err) {
            console.error('fetch table state failed', err);
        }
    }, [guestToken, roomId, handleAuthFailure]);

    useEffect(() => { fetchTableState(); }, [fetchTableState]);

    // Whether the server can route a seat to a trained RL agent. Polled every
    // 10s (the backend health check caches ~5s) so the option appears or
    // disappears as the model server comes up or goes down, without a page
    // refresh. Best-effort: on a transient error we keep the last known value.
    useEffect(() => {
        let cancelled = false;

        const probe = async () => {
            try {
                const res = await fetch(getApiUrl('/api/v1/config'));
                if (!res.ok) return;
                const data = await res.json();
                if (!cancelled) setRlAgentAvailable(Boolean(data?.rlAgentAvailable));
            } catch {
                // capability probe is optional; keep the last known value
            }
        };

        probe();
        const timer = window.setInterval(probe, 10000);
        return () => {
            cancelled = true;
            window.clearInterval(timer);
        };
    }, []);

    useEffect(() => {
        if (!socket || !isConnected) return;

        const handle = (e: MessageEvent) => {
            if (typeof e.data !== 'string') return;
            try {
                const data = JSON.parse(e.data);
                if (data.type === 'lobby_update' && data.room === roomId && data.state) {
                    setTableState(data.state as PrivateTableState);
                    if (data.state.state === 'started' && data.state.matchId) {
                        navigate(`/match/${data.state.matchId}`);
                    }
                }
            } catch (err) {
                // ignore non-JSON / non-lobby payloads
            }
        };

        socket.addEventListener('message', handle);
        return () => socket.removeEventListener('message', handle);
    }, [socket, isConnected, roomId, navigate]);

    const performJoin = useCallback(async (token: string) => {
        if (!roomId) return;
        try {
            const res = await fetch(getApiUrl(`/api/v1/rooms/${roomId}/join`), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
                body: JSON.stringify({}),
            });
            if (res.status === 401) {
                handleAuthFailure();
                return;
            }
            const data = await res.json().catch(() => ({}));
            if (res.status === 409) {
                setError(data.error || 'This private table is already in an active game.');
                return;
            }
            if (!res.ok) {
                setError(data.error || 'Failed to join private table');
                return;
            }
            if (data.status === 'active' && data.matchId) {
                navigate(`/match/${data.matchId}`);
                return;
            }
            setTableState(data as PrivateTableState);
        } catch (err: any) {
            setError(err.message || 'Failed to join private table');
        }
    }, [navigate, roomId, handleAuthFailure]);

    const handleGuestJoin = async () => {
        if (!username.trim() || !roomId) return;
        setError('');
        setJoining(true);
        try {
            const authRes = await fetch(getApiUrl('/api/v1/auth/guest'), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username }),
            });
            const authData = await authRes.json();
            if (!authRes.ok) throw new Error(authData.error || 'Guest auth failed');

            setGuestToken(authData.token);
            savePrivateRoomSession({
                tableId: roomId,
                token: authData.token,
                username: authData.user?.username || username.trim(),
            });
            connect(authData.token);
            await performJoin(authData.token);
        } catch (err: any) {
            setError(err.message);
        } finally {
            setJoining(false);
        }
    };

    const mutateSeat = useCallback(async (seat: number, kind: 'bot' | 'empty', difficulty?: Difficulty) => {
        if (!roomId || !guestToken) return;
        try {
            const res = await fetch(getApiUrl(`/api/v1/rooms/${roomId}/seat`), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${guestToken}` },
                body: JSON.stringify({ seat, kind, difficulty: difficulty ?? game.Difficulty.DIFFICULTY_UNSPECIFIED }),
            });
            if (res.status === 401) {
                handleAuthFailure();
                return;
            }
            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                setError(data.error || 'Failed to update seat');
            }
        } catch (err: any) {
            setError(err.message || 'Failed to update seat');
        }
    }, [guestToken, roomId, handleAuthFailure]);

    const setMatchMode = useCallback(async (mode: 'classic' | 'chongci', cfg?: { starting_score: number; bust_threshold: number; max_hands: number }) => {
        if (!roomId || !guestToken) return;
        try {
            const res = await fetch(getApiUrl(`/api/v1/rooms/${roomId}/mode`), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${guestToken}` },
                body: JSON.stringify({ mode, chongci_config: cfg }),
            });
            if (res.status === 401) {
                handleAuthFailure();
                return;
            }
            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                setError(data.error || 'Failed to update match mode');
            }
        } catch (err: any) {
            setError(err.message || 'Failed to update match mode');
        }
    }, [guestToken, roomId, handleAuthFailure]);

    useEffect(() => {
        const cfg = tableState?.chongciConfig;
        if (cfg) {
            setChongciDraft({
                starting_score: Number(cfg.startingScore ?? 2000),
                bust_threshold: Number(cfg.bustThreshold ?? 0),
                max_hands: Number(cfg.maxHands ?? 50),
            });
        }
    }, [tableState?.chongciConfig]);

    const handleStart = async () => {
        // Guard re-entry: once a start is in flight the table flips to
        // "started" and is removed from the configuring registry, so a second
        // request would 409/404 ("table not found"). One click only.
        if (!roomId || !guestToken || starting) return;
        setStarting(true);
        setError('');
        try {
            const res = await fetch(getApiUrl(`/api/v1/rooms/${roomId}/start`), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${guestToken}` },
                body: JSON.stringify({}),
            });
            if (res.status === 401) {
                handleAuthFailure();
                setStarting(false);
                return;
            }
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                setError(data.error || 'Failed to start match');
                setStarting(false);
                return;
            }
            // The success body already carries the started state + matchId, so
            // navigate immediately rather than waiting for the lobby_update
            // WebSocket broadcast. Keep `starting` true through the redirect.
            if (data.matchId) {
                navigate(`/match/${data.matchId}`);
                return;
            }
            // No matchId in the response (unexpected): fall back to the
            // broadcast-driven redirect, but re-enable the button.
            setStarting(false);
        } catch (err: any) {
            setError(err.message || 'Failed to start match');
            setStarting(false);
        }
    };

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

    const seats = tableState?.seats ?? [];
    const hostUserId = Number(tableState?.hostUserId ?? 0);
    const iAmHost = myUserId !== null && myUserId === hostUserId;
    const allSeatsFilled = seats.length === 4 && seats.every(s => s.kind === 'human' || s.kind === 'bot');

    const filledCount = seats.filter(s => s.kind === 'human' || s.kind === 'bot').length;
    const currentMode = tableState?.matchMode ?? 1; // 1 = CLASSIC
    const isChongci = currentMode === 2;
    const modeLocked = !iAmHost || tableState?.state === 'started';

    return (
        <Page>
            <Shell wide>
                <Card>
                    <PageHeader
                        title="Room"
                        subtitle={roomId}
                        nav={iAmHost && (
                            <Button variant="primary" onClick={handleStart} disabled={!allSeatsFilled || starting}>
                                {starting ? 'Starting…' : 'Start Match'}
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
                                    rlAgentAvailable={rlAgentAvailable}
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
}

function useMyUserId(token: string): number | null {
    const [userId, setUserId] = useState<number | null>(null);
    useEffect(() => {
        if (!token) { setUserId(null); return; }
        const parts = token.split('.');
        if (parts.length !== 3) { setUserId(null); return; }
        try {
            const payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')));
            const sub = typeof payload.sub === 'number' ? payload.sub : Number(payload.sub);
            setUserId(Number.isFinite(sub) ? sub : null);
        } catch {
            setUserId(null);
        }
    }, [token]);
    return userId;
}
