import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

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

        return `${window.location.origin}/table/${roomId}`;
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

    return (
        <div className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(16,185,129,0.18),_transparent_28%),linear-gradient(180deg,_#020617_0%,_#052e2b_55%,_#03131f_100%)] text-white">
            <div className="mx-auto flex min-h-screen w-full max-w-4xl items-center px-6 py-10">
                <div className="grid w-full gap-6 lg:grid-cols-[1.1fr_0.9fr]">
                    <section className="rounded-[28px] border border-emerald-400/20 bg-slate-950/70 p-8 shadow-[0_28px_80px_rgba(0,0,0,0.38)] backdrop-blur-sm">
                        <p className="mb-3 text-xs font-black uppercase tracking-[0.35em] text-emerald-300/75">Private Table</p>
                        <h1 className="mb-4 text-4xl font-black uppercase tracking-[0.12em] text-emerald-200">Create Room</h1>
                        <p className="max-w-xl text-sm leading-7 text-slate-300">
                            Generate a private table link, send it to your friends, and have everyone join the same room from anywhere.
                            No matchmaking queue is needed for this flow.
                        </p>

                        <div className="mt-8 flex flex-wrap gap-3">
                            <button
                                onClick={handleCreateRoom}
                                className="rounded-2xl border border-emerald-300/30 bg-emerald-600 px-6 py-3 text-sm font-black uppercase tracking-[0.18em] text-white shadow-[0_18px_36px_rgba(5,150,105,0.32)] transition-transform hover:-translate-y-0.5 hover:bg-emerald-500"
                            >
                                {roomId ? 'Create Another Link' : 'Generate Link'}
                            </button>
                            {roomUrl && (
                                <Link
                                    to={`/table/${roomId}`}
                                    className="rounded-2xl border border-cyan-300/25 bg-cyan-950/70 px-6 py-3 text-sm font-black uppercase tracking-[0.18em] text-cyan-100 transition-transform hover:-translate-y-0.5 hover:bg-cyan-900/80"
                                >
                                    Open Room
                                </Link>
                            )}
                        </div>

                        <div className="mt-8 rounded-[22px] border border-white/10 bg-slate-900/65 p-5">
                            <div className="mb-3 flex items-center justify-between gap-3">
                                <span className="text-xs font-black uppercase tracking-[0.28em] text-slate-400">Share Link</span>
                                {copyState === 'copied' && <span className="text-xs font-bold uppercase tracking-[0.18em] text-emerald-300">Copied</span>}
                                {copyState === 'failed' && <span className="text-xs font-bold uppercase tracking-[0.18em] text-rose-300">Copy Failed</span>}
                            </div>

                            <div className="rounded-2xl border border-emerald-400/14 bg-black/20 px-4 py-4">
                                {roomUrl ? (
                                    <p className="break-all font-mono text-sm leading-7 text-emerald-100">{roomUrl}</p>
                                ) : (
                                    <p className="text-sm leading-7 text-slate-400">Generate a room link first, then copy or open it.</p>
                                )}
                            </div>

                            <div className="mt-4 flex flex-wrap gap-3">
                                <button
                                    onClick={handleCopy}
                                    disabled={!roomUrl}
                                    className="rounded-2xl border border-white/10 bg-slate-800 px-5 py-3 text-sm font-bold uppercase tracking-[0.16em] text-slate-100 transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
                                >
                                    Copy Link
                                </button>
                                {roomUrl && (
                                    <a
                                        href={roomUrl}
                                        className="rounded-2xl border border-white/10 bg-slate-800 px-5 py-3 text-sm font-bold uppercase tracking-[0.16em] text-slate-100 transition hover:bg-slate-700"
                                    >
                                        Join This Table
                                    </a>
                                )}
                            </div>
                        </div>
                    </section>

                    <aside className="rounded-[28px] border border-white/10 bg-slate-950/55 p-8 shadow-[0_22px_64px_rgba(0,0,0,0.3)] backdrop-blur-sm">
                        <p className="mb-4 text-xs font-black uppercase tracking-[0.32em] text-cyan-300/80">How It Works</p>
                        <div className="space-y-5 text-sm leading-7 text-slate-300">
                            <p>1. Generate a private link here.</p>
                            <p>2. Send the link to your friends.</p>
                            <p>3. Everyone opens the same `/table/...` link and enters a temporary name.</p>
                            <p>4. The host (first joiner) fills any empty seats with AI and clicks Start when ready.</p>
                        </div>

                        <div className="mt-8 rounded-2xl border border-amber-300/18 bg-amber-950/25 px-4 py-4 text-sm leading-7 text-amber-100/90">
                            Any table ID works as a private room key. This page just gives you a clean share link without exposing matchmaking.
                        </div>

                        <div className="mt-8 flex flex-wrap gap-3">
                            <Link
                                to="/"
                                className="rounded-2xl border border-white/10 bg-white/5 px-5 py-3 text-sm font-bold uppercase tracking-[0.14em] text-slate-100 transition hover:bg-white/10"
                            >
                                Back To Login
                            </Link>
                            <Link
                                to="/lobby"
                                className="rounded-2xl border border-white/10 bg-white/5 px-5 py-3 text-sm font-bold uppercase tracking-[0.14em] text-slate-100 transition hover:bg-white/10"
                            >
                                Matchmaking
                            </Link>
                        </div>
                    </aside>
                </div>
            </div>
        </div>
    );
}
