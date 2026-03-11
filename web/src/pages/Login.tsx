import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useSocket } from '../contexts/SocketContext';
import { getApiUrl } from '../config';

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
            navigate('/lobby');
        } catch (err: any) {
            setError(err.message);
        }
    };

    return (
        <div className="min-h-screen bg-[radial-gradient(circle_at_50%_20%,_rgba(16,185,129,0.2),_transparent_24%),linear-gradient(180deg,_#04111a_0%,_#07382f_58%,_#031018_100%)] text-white">
            <div className="mx-auto flex min-h-screen w-full max-w-6xl items-center px-6 py-10">
                <div className="grid w-full gap-6 lg:grid-cols-[0.95fr_1.05fr]">
                    <aside className="rounded-[30px] border border-white/10 bg-slate-950/62 p-8 shadow-[0_22px_70px_rgba(0,0,0,0.3)] backdrop-blur-sm">
                        <p className="text-[11px] font-black uppercase tracking-[0.34em] text-emerald-300/78">Fenghua Mahjong</p>
                        <h1 className="mt-4 text-4xl font-black uppercase tracking-[0.12em] text-emerald-100 sm:text-5xl">Enter The Table</h1>
                        <p className="mt-5 text-sm leading-8 text-slate-300">
                            Login for matchmaking, or jump straight into a private room flow and send the room link to your friends.
                        </p>

                        <div className="mt-8 grid gap-3 sm:grid-cols-2">
                            <div className="rounded-[24px] border border-emerald-300/16 bg-emerald-500/8 px-5 py-5">
                                <p className="text-[11px] font-black uppercase tracking-[0.26em] text-emerald-200/88">Public Queue</p>
                                <p className="mt-3 text-sm leading-7 text-slate-300">Use the lobby to find a live hometown-rules table automatically.</p>
                            </div>
                            <div className="rounded-[24px] border border-cyan-300/16 bg-cyan-500/8 px-5 py-5">
                                <p className="text-[11px] font-black uppercase tracking-[0.26em] text-cyan-100">Private Room</p>
                                <p className="mt-3 text-sm leading-7 text-slate-300">Generate a `/table/...` link and gather exactly the four players you want.</p>
                            </div>
                        </div>

                        <div className="mt-8 flex flex-wrap gap-3">
                            <Link
                                to="/create-room"
                                className="rounded-[24px] border border-cyan-300/20 bg-cyan-950/60 px-6 py-3 text-xs font-black uppercase tracking-[0.18em] text-cyan-100 transition hover:-translate-y-0.5 hover:bg-cyan-900/70"
                            >
                                Create Private Room
                            </Link>
                        </div>
                    </aside>

                    <section className="rounded-[30px] border border-emerald-300/20 bg-slate-950/72 p-8 shadow-[0_28px_80px_rgba(0,0,0,0.38)] backdrop-blur-sm">
                        <p className="text-[11px] font-black uppercase tracking-[0.34em] text-emerald-300/78">Account Access</p>
                        <h2 className="mt-4 text-3xl font-black uppercase tracking-[0.12em] text-emerald-100">Login Or Register</h2>

                        {error && (
                            <div className="mt-5 rounded-2xl border border-rose-400/28 bg-rose-950/28 px-4 py-3 text-sm text-rose-100">
                                {error}
                            </div>
                        )}

                        <div className="mt-6 space-y-4">
                            <input
                                className="w-full rounded-[20px] border border-white/10 bg-slate-900/90 px-4 py-3 text-white outline-none transition focus:border-emerald-400/50 focus:bg-slate-950"
                                placeholder="Username"
                                value={username}
                                onChange={e => setUsername(e.target.value)}
                            />
                            <input
                                type="password"
                                className="w-full rounded-[20px] border border-white/10 bg-slate-900/90 px-4 py-3 text-white outline-none transition focus:border-emerald-400/50 focus:bg-slate-950"
                                placeholder="Password"
                                value={password}
                                onChange={e => setPassword(e.target.value)}
                            />
                        </div>

                        <div className="mt-6 flex flex-wrap gap-4">
                            <button
                                className="rounded-[24px] border border-emerald-300/24 bg-emerald-600 px-7 py-3 text-sm font-black uppercase tracking-[0.18em] text-white shadow-[0_20px_40px_rgba(5,150,105,0.32)] transition hover:-translate-y-0.5 hover:bg-emerald-500"
                                onClick={() => handleAuth(true)}
                            >
                                Login
                            </button>
                            <button
                                className="rounded-[24px] border border-white/10 bg-slate-800/85 px-7 py-3 text-sm font-black uppercase tracking-[0.18em] text-slate-100 transition hover:-translate-y-0.5 hover:bg-slate-700"
                                onClick={() => handleAuth(false)}
                            >
                                Register
                            </button>
                        </div>
                    </section>
                </div>
            </div>
        </div>
    );
}
