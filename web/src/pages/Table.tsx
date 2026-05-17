// @ts-nocheck
import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useSocket } from '../contexts/SocketContext';
import { useGameState } from '../contexts/GameContext';
import { getApiUrl } from '../config';
import { clearPrivateRoomSession, loadPrivateRoomSession, savePrivateRoomSession } from './privateRoomSession';
import SeatCard from './SeatCard';
import { game } from '../proto/game';

type PrivateTableState = game.IPrivateTableState;
type Difficulty = game.Difficulty;

export default function Table() {
    const { tableId } = useParams();
    const [username, setUsername] = useState(() => loadPrivateRoomSession(tableId)?.username ?? '');
    const [guestToken, setGuestToken] = useState('');
    const [joining, setJoining] = useState(false);
    const [error, setError] = useState('');
    const [tableState, setTableState] = useState<PrivateTableState | null>(null);

    const navigate = useNavigate();
    const { isConnected, connect, socket } = useSocket();
    const { gameState } = useGameState();

    const myUserId = useMyUserId(guestToken);

    useEffect(() => {
        if (gameState && gameState.matchId) {
            navigate(`/game/${gameState.matchId}`);
        }
    }, [gameState, navigate]);

    useEffect(() => {
        const stored = loadPrivateRoomSession(tableId);
        if (stored && !isConnected) {
            setGuestToken(stored.token);
            setUsername(stored.username);
            connect(stored.token);
        }
    }, [connect, isConnected, tableId]);

    const handleAuthFailure = useCallback(() => {
        clearPrivateRoomSession(tableId);
        setGuestToken('');
        setTableState(null);
        setError('Your private room session expired. Enter your name again.');
    }, [tableId]);

    const fetchTableState = useCallback(async () => {
        if (!tableId || !guestToken) return;
        try {
            const res = await fetch(getApiUrl(`/api/v1/private-tables/${tableId}`), {
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
    }, [guestToken, tableId, handleAuthFailure]);

    useEffect(() => { fetchTableState(); }, [fetchTableState]);

    useEffect(() => {
        if (!socket || !isConnected) return;

        const handle = (e: MessageEvent) => {
            if (typeof e.data !== 'string') return;
            try {
                const data = JSON.parse(e.data);
                if (data.type === 'lobby_update' && data.table === tableId && data.state) {
                    setTableState(data.state as PrivateTableState);
                    if (data.state.state === 'started' && data.state.matchId) {
                        navigate(`/game/${data.state.matchId}`);
                    }
                }
            } catch (err) {
                // ignore non-JSON / non-lobby payloads
            }
        };

        socket.addEventListener('message', handle);
        return () => socket.removeEventListener('message', handle);
    }, [socket, isConnected, tableId, navigate]);

    const performJoin = useCallback(async (token: string) => {
        if (!tableId) return;
        try {
            const res = await fetch(getApiUrl(`/api/v1/private-tables/${tableId}/join`), {
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
                navigate(`/game/${data.matchId}`);
                return;
            }
            setTableState(data as PrivateTableState);
        } catch (err: any) {
            setError(err.message || 'Failed to join private table');
        }
    }, [navigate, tableId, handleAuthFailure]);

    const handleGuestJoin = async () => {
        if (!username.trim() || !tableId) return;
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
                tableId,
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
        if (!tableId || !guestToken) return;
        try {
            const res = await fetch(getApiUrl(`/api/v1/private-tables/${tableId}/seat`), {
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
    }, [guestToken, tableId, handleAuthFailure]);

    const handleStart = async () => {
        if (!tableId || !guestToken) return;
        try {
            const res = await fetch(getApiUrl(`/api/v1/private-tables/${tableId}/start`), {
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
            <div className="min-h-screen bg-[radial-gradient(circle_at_50%_18%,_rgba(16,185,129,0.18),_transparent_22%),linear-gradient(180deg,_#03111a_0%,_#06352d_58%,_#041019_100%)] text-white">
                <div className="mx-auto flex min-h-screen w-full max-w-2xl flex-col items-center justify-center px-6 py-10">
                    <div className="w-full rounded-[28px] border border-emerald-300/20 bg-slate-950/70 p-8 shadow-[0_22px_70px_rgba(0,0,0,0.3)]">
                        <p className="text-[11px] font-black uppercase tracking-[0.32em] text-emerald-300/78">Private Table</p>
                        <h1 className="mt-2 text-3xl font-black uppercase tracking-[0.12em] text-emerald-100">Join Table {tableId}</h1>
                        <p className="mt-4 text-sm leading-7 text-slate-300">Pick a display name to enter as a guest.</p>
                        <input
                            value={username}
                            onChange={e => setUsername(e.target.value)}
                            placeholder="Your name"
                            className="mt-6 w-full rounded-2xl border border-emerald-300/20 bg-slate-900/60 px-4 py-3 text-sm text-emerald-100 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-emerald-400/40"
                        />
                        {error && <div className="mt-4 rounded-2xl border border-rose-400/30 bg-rose-950/30 px-4 py-3 text-sm text-rose-100">{error}</div>}
                        <button
                            onClick={handleGuestJoin}
                            disabled={joining || !username.trim()}
                            className="mt-6 w-full rounded-2xl border border-emerald-300/30 bg-emerald-600 px-5 py-3 text-sm font-black uppercase tracking-[0.18em] text-white shadow-[0_18px_38px_rgba(5,150,105,0.32)] hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                            {joining ? 'Joining…' : 'Join Table'}
                        </button>
                    </div>
                </div>
            </div>
        );
    }

    const seats = tableState?.seats ?? [];
    const hostUserId = Number(tableState?.hostUserId ?? 0);
    const iAmHost = myUserId !== null && myUserId === hostUserId;
    const allSeatsFilled = seats.length === 4 && seats.every(s => s.kind === 'human' || s.kind === 'bot');

    return (
        <div className="min-h-screen bg-[radial-gradient(circle_at_50%_18%,_rgba(16,185,129,0.18),_transparent_22%),linear-gradient(180deg,_#03111a_0%,_#06352d_58%,_#041019_100%)] text-white">
            <div className="mx-auto flex min-h-screen w-full max-w-4xl flex-col px-6 py-10">
                <header className="mb-6 flex items-center justify-between">
                    <div>
                        <p className="text-[11px] font-black uppercase tracking-[0.32em] text-emerald-300/78">Private Table</p>
                        <h1 className="mt-1 text-3xl font-black uppercase tracking-[0.12em] text-emerald-100">Table {tableId}</h1>
                    </div>
                    {iAmHost && (
                        <button
                            onClick={handleStart}
                            disabled={!allSeatsFilled}
                            className="rounded-2xl border border-emerald-300/30 bg-emerald-600 px-5 py-3 text-sm font-black uppercase tracking-[0.18em] text-white shadow-[0_18px_38px_rgba(5,150,105,0.32)] hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                            Start Match
                        </button>
                    )}
                </header>

                {error && <div className="mb-4 rounded-2xl border border-rose-400/30 bg-rose-950/30 px-4 py-3 text-sm text-rose-100">{error}</div>}

                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
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
                    <p className="mt-6 text-sm text-slate-300">Fill every seat with a player or AI before starting.</p>
                )}
                {!iAmHost && (
                    <p className="mt-6 text-sm text-slate-300">The host configures the table. You'll join automatically when the match begins.</p>
                )}
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
