// @ts-nocheck
import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useSocket } from '../contexts/SocketContext';
import { useGameState } from '../contexts/GameContext';
import { getApiUrl } from '../config';
import { clearPrivateRoomSession, loadPrivateRoomSession, savePrivateRoomSession } from './privateRoomSession';
import SeatCard from './SeatCard';
import { game } from '../proto/game';
import './ledger-theme.css';

type PrivateTableState = game.IPrivateTableState;
type Difficulty = game.Difficulty;

export default function Table() {
    const { roomId } = useParams();
    const [username, setUsername] = useState(() => loadPrivateRoomSession(roomId)?.username ?? '');
    const [guestToken, setGuestToken] = useState('');
    const [joining, setJoining] = useState(false);
    const [error, setError] = useState('');
    const [tableState, setTableState] = useState<PrivateTableState | null>(null);
    const [chongciDraft, setChongciDraft] = useState({ starting_score: 2000, bust_threshold: 0, max_hands: 50 });

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
        if (!roomId || !guestToken) return;
        try {
            const res = await fetch(getApiUrl(`/api/v1/rooms/${roomId}/start`), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${guestToken}` },
                body: JSON.stringify({}),
            });
            if (res.status === 401) {
                handleAuthFailure();
                return;
            }
            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                setError(data.error || 'Failed to start match');
            }
        } catch (err: any) {
            setError(err.message || 'Failed to start match');
        }
    };

    if (!guestToken) {
        return (
            <div className="ledger-page">
                <div className="ledger-shell">
                    <article className="ldg-page">
                        <div className="ldg-page-head">
                            <div>
                                <h1 className="ldg-page-head__title">
                                    Join Room
                                    <small>{roomId}</small>
                                </h1>
                            </div>
                        </div>

                        <section className="ldg-section">
                            <div className="ldg-section-row">
                                <h2 className="ldg-section-title">
                                    Enter as guest
                                    <small>Pick a display name to join this private room.</small>
                                </h2>
                            </div>
                            <div className="ldg-field">
                                <label className="ldg-field__label">Display name</label>
                                <input
                                    className="ldg-input"
                                    value={username}
                                    onChange={e => setUsername(e.target.value)}
                                    placeholder="Your name"
                                />
                            </div>
                            {error && <p className="ldg-note ldg-note--err">{error}</p>}
                            <div className="ldg-tools-row" style={{ marginTop: '1rem' }}>
                                <button
                                    className="ldg-btn ldg-btn--primary"
                                    onClick={handleGuestJoin}
                                    disabled={joining || !username.trim()}
                                >
                                    {joining ? 'Joining…' : 'Join Room'}
                                </button>
                            </div>
                        </section>
                    </article>
                </div>
            </div>
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
        <div className="ledger-page">
            <div className="ledger-shell ledger-shell--wide">
                <article className="ldg-page">
                    <div className="ldg-page-head">
                        <div>
                            <h1 className="ldg-page-head__title">
                                Room
                                <small>{roomId}</small>
                            </h1>
                        </div>
                        <div className="ldg-page-head__nav">
                            {iAmHost && (
                                <button
                                    className="ldg-btn ldg-btn--primary"
                                    onClick={handleStart}
                                    disabled={!allSeatsFilled}
                                >
                                    Start Match
                                </button>
                            )}
                        </div>
                    </div>

                    {error && <p className="ldg-note ldg-note--err">{error}</p>}

                    <section className="ldg-section">
                        <div className="ldg-section-row">
                            <h2 className="ldg-section-title">Match mode</h2>
                        </div>
                        <div className="ldg-toggle">
                            <button
                                className={`ldg-toggle__btn ${!isChongci ? 'is-active' : ''}`}
                                disabled={modeLocked}
                                onClick={() => setMatchMode('classic')}
                            >
                                Classic
                            </button>
                            <button
                                className={`ldg-toggle__btn ${isChongci ? 'is-active' : ''}`}
                                disabled={modeLocked}
                                onClick={() => setMatchMode('chongci', chongciDraft)}
                            >
                                Chongci
                            </button>
                        </div>
                        {isChongci && (
                            <div className="ldg-grid-3" style={{ marginTop: '0.85rem' }}>
                                {[
                                    { key: 'starting_score', label: 'Starting points', min: 100, max: 1_000_000 },
                                    { key: 'bust_threshold', label: 'Bust threshold', min: -1_000_000, max: 0 },
                                    { key: 'max_hands', label: 'Max hands (0=∞)', min: 0, max: 200 },
                                ].map(({ key, label, min, max }) => (
                                    <div className="ldg-field" key={key}>
                                        <label className="ldg-field__label">{label}</label>
                                        <input
                                            type="number"
                                            className="ldg-input"
                                            min={min}
                                            max={max}
                                            value={(chongciDraft as any)[key]}
                                            disabled={modeLocked}
                                            onChange={e => setChongciDraft(d => ({ ...d, [key]: Number(e.target.value) }))}
                                            onBlur={() => iAmHost && setMatchMode('chongci', chongciDraft)}
                                        />
                                    </div>
                                ))}
                            </div>
                        )}
                        {!iAmHost && (
                            <p className="ldg-note">Only the host can change match settings.</p>
                        )}
                    </section>

                    <section className="ldg-section">
                        <div className="ldg-section-row">
                            <h2 className="ldg-section-title">Seats</h2>
                            <span className="ldg-section-meta">{filledCount} / 4</span>
                        </div>
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

                        {iAmHost && !allSeatsFilled && (
                            <p className="ldg-note">Fill every seat with a player or AI before starting.</p>
                        )}
                        {!iAmHost && (
                            <p className="ldg-note">The host configures the table. You'll join automatically when the match begins.</p>
                        )}
                    </section>
                </article>
            </div>
        </div>
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
