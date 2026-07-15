// @ts-nocheck
import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useSocket } from '../../contexts/SocketContext';
import { useAuth } from '../../contexts/AuthContext';
import { getApiUrl } from '../../config';
import { roomActiveRedirectMatchId } from './roomNavigation';
import { savePrivateRoomSession } from './privateRoomSession';
import {
    clearLeftMatchMarker,
    loadLeftMatchMarker,
    saveLeftMatchMarker,
} from './rejoinMatch';
import type { LeftMatchMarker } from './rejoinMatch';
import SeatCard from './SeatCard';
import { game } from '../../proto/game';
import { ClubShell, Card, PageHeader, Section, ToolsRow, Button, Field, Note, Toggle } from '../../theme';

type PrivateTableState = game.IPrivateTableState;
type Difficulty = game.Difficulty;

export default function Table() {
    const { roomId } = useParams();
    const [joining, setJoining] = useState(false);
    const [starting, setStarting] = useState(false);
    const [error, setError] = useState('');
    const [tableState, setTableState] = useState<PrivateTableState | null>(null);
    const [activeMatchId, setActiveMatchId] = useState('');
    const [chongciDraft, setChongciDraft] = useState({ starting_score: 2000, bust_threshold: 0, max_hands: 50 });
    const [rlAgentAvailable, setRlAgentAvailable] = useState(false);
    const [leftMarker, setLeftMarker] = useState<LeftMatchMarker | null>(() => loadLeftMatchMarker());
    const [shareState, setShareState] = useState<'idle' | 'copied' | 'failed'>('idle');

    const navigate = useNavigate();
    const { isConnected, connect, socket } = useSocket();
    const { status: authStatus, user, apiFetch, refreshSession } = useAuth();
    const myUserId = user?.id ?? null;

    // The left-match marker is stored globally; only honor it for the room it
    // actually belongs to, so a leave in one room never suppresses connect /
    // redirect (or shows the Rejoin banner) in a different room. This is the
    // same object reference as `leftMarker` or null, so it is stable across
    // renders and safe in effect dependency lists.
    const roomLeftMarker = leftMarker && leftMarker.roomId === roomId ? leftMarker : null;

    useEffect(() => {
        if (authStatus === 'anonymous' && roomId) {
            navigate(`/login?returnTo=${encodeURIComponent(`/room/${roomId}`)}`, { replace: true });
        } else if (authStatus === 'authenticated' && !roomLeftMarker) {
            connect();
        }
    }, [authStatus, connect, navigate, roomId, roomLeftMarker]);

    // If the match ended (or the room is back to configuring) while we were
    // away, drop the marker so the normal room screen shows instead of Rejoin.
    useEffect(() => {
        if (roomLeftMarker && tableState && tableState.state !== 'started') {
            clearLeftMatchMarker();
            setLeftMarker(null);
        }
    }, [roomLeftMarker, tableState]);

    const handleRejoin = useCallback(() => {
        const matchId = roomLeftMarker?.matchId || (tableState as any)?.matchId;
        clearLeftMatchMarker();
        setLeftMarker(null);
        connect();
        if (matchId) navigate(`/match/${matchId}`);
    }, [connect, navigate, roomLeftMarker, tableState]);

    const copyTableLink = useCallback(async () => {
        if (!roomId || typeof window === 'undefined') return;
        try {
            await navigator.clipboard.writeText(`${window.location.origin}/room/${roomId}`);
            setShareState('copied');
        } catch {
            setShareState('failed');
        }
    }, [roomId]);

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
                    if (!roomLeftMarker && data.state.state === 'started' && data.state.matchId) {
                        navigate(`/match/${data.state.matchId}`);
                    } else if (roomLeftMarker && data.state.state === 'started' && data.state.matchId) {
                        setActiveMatchId(data.state.matchId);
                    }
                }
            } catch (err) {
                // ignore non-JSON / non-lobby payloads
            }
        };

        socket.addEventListener('message', handle);
        return () => socket.removeEventListener('message', handle);
    }, [socket, isConnected, roomId, navigate, roomLeftMarker]);

    const performJoin = useCallback(async (signal?: AbortSignal) => {
        if (!roomId) return;
        setJoining(true);
        setError('');
        try {
            const res = await apiFetch(`/api/v1/rooms/${roomId}/join`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({}),
                signal,
            });
            if (signal?.aborted) return;
            const data = await res.json().catch(() => ({}));
            if (res.status === 401) {
                navigate(`/login?returnTo=${encodeURIComponent(`/room/${roomId}`)}`, { replace: true });
                return;
            }
            if (!res.ok) {
                if (res.status === 404) setError('This private table is unavailable. Ask the host for a new link.');
                else if (res.status === 409) setError(data.error || 'This table is full or already playing.');
                else setError(data.error || 'Failed to join private table');
                return;
            }
            const matchId = roomActiveRedirectMatchId(data, leftMarker, roomId);
            if (matchId) {
                navigate(`/match/${matchId}`);
                return;
            }
            if (data.status === 'active' && data.matchId) {
                setActiveMatchId(data.matchId);
                if (roomLeftMarker && roomLeftMarker.matchId !== data.matchId) {
                    const updated = { roomId, matchId: data.matchId };
                    saveLeftMatchMarker(updated);
                    setLeftMarker(updated);
                }
                return;
            }
            setActiveMatchId('');
            setTableState(data as PrivateTableState);
            savePrivateRoomSession({ tableId: roomId });
        } catch (err: any) {
            if (err?.name === 'AbortError') return;
            setError(err instanceof TypeError ? 'The club is offline. Your invitation is unchanged.' : err.message || 'Failed to join private table');
        } finally {
            if (!signal?.aborted) setJoining(false);
        }
    }, [apiFetch, leftMarker, navigate, roomId, roomLeftMarker]);

    useEffect(() => {
        if (authStatus !== 'authenticated') return;
        const controller = new AbortController();
        void performJoin(controller.signal);
        return () => controller.abort();
    }, [authStatus, performJoin]);

    const mutateSeat = useCallback(async (seat: number, kind: 'bot' | 'empty', difficulty?: Difficulty) => {
        if (!roomId || authStatus !== 'authenticated') return;
        try {
            const res = await apiFetch(`/api/v1/rooms/${roomId}/seat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ seat, kind, difficulty: difficulty ?? game.Difficulty.DIFFICULTY_UNSPECIFIED }),
            });
            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                setError(data.error || 'Failed to update seat');
            }
        } catch (err: any) {
            setError(err.message || 'Failed to update seat');
        }
    }, [apiFetch, authStatus, roomId]);

    const setMatchMode = useCallback(async (mode: 'classic' | 'chongci', cfg?: { starting_score: number; bust_threshold: number; max_hands: number }) => {
        if (!roomId || authStatus !== 'authenticated') return;
        try {
            const res = await apiFetch(`/api/v1/rooms/${roomId}/mode`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mode, chongci_config: cfg }),
            });
            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                setError(data.error || 'Failed to update match mode');
            }
        } catch (err: any) {
            setError(err.message || 'Failed to update match mode');
        }
    }, [apiFetch, authStatus, roomId]);

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
        if (!roomId || authStatus !== 'authenticated' || starting) return;
        setStarting(true);
        setError('');
        try {
            const res = await apiFetch(`/api/v1/rooms/${roomId}/start`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({}),
            });
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

    const showingRejoin = Boolean(roomLeftMarker && activeMatchId);

    if (authStatus === 'offline') {
        return (
            <ClubShell title="Private Table">
                <Card>
                    <PageHeader title="The club is offline" subtitle={roomId} />
                    <Section title="Your invitation is safe" subtitle="Reconnect, then we’ll check this exact table again.">
                        <ToolsRow><Button variant="primary" onClick={() => void refreshSession()}>Try Again</Button></ToolsRow>
                    </Section>
                </Card>
            </ClubShell>
        );
    }

    if (authStatus !== 'authenticated' || joining || (!tableState && !showingRejoin)) {
        return (
            <ClubShell title="Private Table">
                    <Card>
                        <PageHeader title={error ? 'Table unavailable' : 'Joining private table'} subtitle={roomId} />
                        <Section title={error ? 'The invitation could not be opened' : 'Taking your seat'} subtitle={error ? 'This link never creates a replacement room.' : 'Your account is confirmed. We’re asking the host’s table for a seat.'}>
                            {error && <Note tone="error">{error}</Note>}
                            {!error && <Note>{authStatus === 'loading' ? 'Checking your club pass…' : 'Joining table…'}</Note>}
                            <ToolsRow>
                                {error && <><Button variant="primary" onClick={() => void performJoin()}>Try Again</Button><Button onClick={() => navigate('/play')}>Back to Play</Button></>}
                            </ToolsRow>
                        </Section>
                    </Card>
            </ClubShell>
        );
    }

    if (showingRejoin) {
        return (
            <ClubShell title="Private Table">
                <Card>
                    <PageHeader title="Match in progress" subtitle={roomId} />
                    <Section title="Your seat is being held" subtitle="A bot is playing while you're away. Rejoin whenever you're ready.">
                        <ToolsRow>
                            <Button variant="primary" onClick={handleRejoin}>Rejoin Match</Button>
                            <Button variant="default" onClick={copyTableLink}>{shareState === 'copied' ? 'Link Copied' : shareState === 'failed' ? 'Copy Failed' : 'Share Table'}</Button>
                        </ToolsRow>
                    </Section>
                </Card>
            </ClubShell>
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
        <ClubShell wide title="Private Table">
                <Card>
                    <PageHeader
                        title="Private Table"
                        subtitle={`${roomId} · ${isChongci ? 'Chongci' : 'Classic Fenghua'}`}
                        nav={<Button onClick={copyTableLink}>{shareState === 'copied' ? 'Link Copied' : shareState === 'failed' ? 'Copy Failed' : 'Share Table'}</Button>}
                    />

                    {error && <Note tone="error">{error}</Note>}

                    <details className="table-rules">
                        <summary>Table Rules <span>{isChongci ? 'Chongci' : 'Classic Fenghua'}</span></summary>
                        <Section title="Game mode">
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
                            {!iAmHost && <Note>Only the host can change table rules.</Note>}
                        </Section>
                    </details>

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

                    <div className="waiting-room__primary">
                        {iAmHost ? (
                            <Button variant="primary" onClick={handleStart} disabled={!allSeatsFilled || starting}>
                                {starting ? 'Starting…' : allSeatsFilled ? 'Start Match' : `Fill ${4 - filledCount} More Seat${4 - filledCount === 1 ? '' : 's'}`}
                            </Button>
                        ) : <span>Waiting for the host to start the match.</span>}
                    </div>
                </Card>
        </ClubShell>
    );
}
