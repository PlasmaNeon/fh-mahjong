import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useSocket } from '../contexts/SocketContext';
import { useGameState } from '../contexts/GameContext';
import { getApiUrl } from '../config';

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
            navigate(`/game/${gameState.matchId}`);
        }
    }, [isConnected, gameState, navigate, connect]);

    const joinQueue = async () => {
        const token = localStorage.getItem('fh_token');
        if (!token) return navigate('/');

        setError('');
        setIsQueuing(true);
        try {
            const res = await fetch(getApiUrl('/api/v1/matchmaking/join'), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`,
                },
                body: JSON.stringify({ ruleset: 'hometown' }),
            });

            if (!res.ok) {
                throw new Error('Failed to join queue');
            }
        } catch (e: any) {
            setError(e.message || 'Error contacting matchmaker');
            setIsQueuing(false);
        }
    };

    return (
        <div className="min-h-screen bg-[radial-gradient(circle_at_50%_18%,_rgba(16,185,129,0.18),_transparent_22%),linear-gradient(180deg,_#03111a_0%,_#06352d_58%,_#041019_100%)] text-white">
            <div className="mx-auto flex min-h-screen w-full max-w-6xl items-center px-6 py-10">
                <div className="grid w-full gap-6 lg:grid-cols-[1.05fr_0.95fr]">
                    <section className="rounded-[30px] border border-emerald-300/20 bg-slate-950/72 p-8 shadow-[0_28px_80px_rgba(0,0,0,0.38)] backdrop-blur-sm">
                        <p className="text-[11px] font-black uppercase tracking-[0.34em] text-emerald-300/78">Matchmaking</p>
                        <h1 className="mt-4 text-4xl font-black uppercase tracking-[0.12em] text-emerald-100 sm:text-5xl">Find A Table</h1>
                        <p className="mt-5 max-w-xl text-sm leading-8 text-slate-300">
                            Queue into the live hometown-rules pool, or jump to a private room flow if you already know who is joining.
                        </p>

                        <div className="mt-8 flex flex-wrap gap-3">
                            <span className={`rounded-full border px-4 py-2 text-[11px] font-black uppercase tracking-[0.24em] ${isConnected ? 'border-emerald-300/26 bg-emerald-500/10 text-emerald-200' : 'border-rose-300/20 bg-rose-500/10 text-rose-200'}`}>
                                {isConnected ? 'Socket Ready' : 'Socket Offline'}
                            </span>
                            <span className="rounded-full border border-cyan-300/20 bg-cyan-500/10 px-4 py-2 text-[11px] font-black uppercase tracking-[0.24em] text-cyan-100">
                                Hometown Rules
                            </span>
                        </div>

                        {error && (
                            <div className="mt-6 rounded-2xl border border-rose-400/28 bg-rose-950/28 px-4 py-3 text-sm text-rose-100">
                                {error}
                            </div>
                        )}

                        {isQueuing ? (
                            <div className="mt-8 rounded-[28px] border border-emerald-300/16 bg-emerald-500/8 px-6 py-8 text-center">
                                <div className="mx-auto h-16 w-16 animate-spin rounded-full border-4 border-emerald-400 border-t-transparent" />
                                <p className="mt-5 text-base font-black uppercase tracking-[0.18em] text-emerald-200">Searching For Players</p>
                                <p className="mt-3 text-sm leading-7 text-slate-300">
                                    Stay on this page. The client will jump straight into the match as soon as the room is ready.
                                </p>
                            </div>
                        ) : (
                            <div className="mt-8 flex flex-wrap gap-4">
                                <button
                                    onClick={joinQueue}
                                    disabled={!isConnected}
                                    className="rounded-[24px] border border-emerald-300/24 bg-emerald-600 px-7 py-4 text-sm font-black uppercase tracking-[0.18em] text-white shadow-[0_20px_40px_rgba(5,150,105,0.32)] transition hover:-translate-y-0.5 hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-45"
                                >
                                    Find Match
                                </button>
                                <Link
                                    to="/create-room"
                                    className="rounded-[24px] border border-cyan-300/20 bg-cyan-950/60 px-7 py-4 text-sm font-black uppercase tracking-[0.18em] text-cyan-100 transition hover:-translate-y-0.5 hover:bg-cyan-900/70"
                                >
                                    Private Room
                                </Link>
                            </div>
                        )}
                    </section>

                    <aside className="rounded-[30px] border border-white/10 bg-slate-950/62 p-8 shadow-[0_22px_70px_rgba(0,0,0,0.3)] backdrop-blur-sm">
                        <p className="text-[11px] font-black uppercase tracking-[0.32em] text-cyan-300/78">Room Flow</p>
                        <div className="mt-6 space-y-5 text-sm leading-7 text-slate-300">
                            <p>1. Login once with your account.</p>
                            <p>2. Use matchmaking for public games, or create a private link for friends.</p>
                            <p>3. Private tables go through the same pre-game room and ready flow as the live table.</p>
                            <p>4. Once a match starts, the table switches into the live game layout automatically.</p>
                        </div>

                        <div className="mt-8 rounded-[24px] border border-amber-300/18 bg-amber-950/24 px-5 py-5 text-sm leading-7 text-amber-100/92">
                            `/table/:tableId` is already the real waiting room route. `/create-room` just gives you a clean way to share it.
                        </div>

                        <div className="mt-8">
                            <Link
                                to="/"
                                className="inline-flex rounded-2xl border border-white/10 bg-white/5 px-5 py-3 text-xs font-black uppercase tracking-[0.16em] text-slate-100 transition hover:bg-white/10"
                            >
                                Back To Login
                            </Link>
                        </div>
                    </aside>
                </div>
            </div>
        </div>
    );
}
