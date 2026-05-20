// @ts-nocheck
import { useNavigate } from 'react-router-dom';
import { game } from '../proto/game';

type Props = {
    state: game.IGameState;
    seatNames: (string | null)[];   // length 4; null for AI seats
};

const reasonLabel = (reason?: string | null) => {
    switch (reason) {
        case 'bust': return 'Match Over — Bust';
        case 'hand_cap': return 'Match Over — Hand cap reached';
        default: return 'Match Over';
    }
};

const rankLabel = (rank: number) => {
    if (rank === 1) return '1st';
    if (rank === 2) return '2nd';
    if (rank === 3) return '3rd';
    return `${rank}th`;
};

export default function MatchEndOverlay({ state, seatNames }: Props) {
    const navigate = useNavigate();
    const result = state.matchEndResult;
    if (!result || !result.standings) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-6">
            <div className="w-full max-w-lg rounded-[28px] border border-emerald-300/20 bg-slate-950/95 p-8 shadow-[0_22px_70px_rgba(0,0,0,0.5)]">
                <p className="text-[11px] font-black uppercase tracking-[0.32em] text-emerald-300/78">Chongci</p>
                <h1 className="mt-2 text-2xl font-black uppercase tracking-[0.12em] text-emerald-100">
                    {reasonLabel(result.reason)}
                </h1>
                <p className="mt-1 text-xs text-slate-400">Final hand: {Number(result.finalHandNum ?? 0)}</p>

                <div className="mt-6 overflow-hidden rounded-2xl border border-slate-800">
                    <table className="w-full text-sm">
                        <thead className="bg-slate-900/80 text-[10px] uppercase tracking-[0.18em] text-emerald-200/70">
                            <tr>
                                <th className="px-4 py-2 text-left">Rank</th>
                                <th className="px-4 py-2 text-left">Player</th>
                                <th className="px-4 py-2 text-right">Score</th>
                                <th className="px-4 py-2 text-right">Δ</th>
                            </tr>
                        </thead>
                        <tbody>
                            {result.standings.map(s => {
                                const seat = Number(s.seat ?? 0);
                                const name = seatNames[seat] ?? `Seat ${seat}`;
                                const net = Number(s.netChange ?? 0);
                                return (
                                    <tr key={seat} className="border-t border-slate-800/80">
                                        <td className="px-4 py-2 font-black text-emerald-100">{rankLabel(Number(s.rank ?? 0))}</td>
                                        <td className="px-4 py-2 text-slate-200">{name}</td>
                                        <td className="px-4 py-2 text-right text-slate-100">{Number(s.finalScore ?? 0)}</td>
                                        <td className={`px-4 py-2 text-right font-mono ${net >= 0 ? 'text-emerald-300' : 'text-rose-300'}`}>
                                            {net >= 0 ? `+${net}` : `${net}`}
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>

                <button
                    onClick={() => navigate('/lobby')}
                    className="mt-6 w-full rounded-2xl border border-emerald-300/30 bg-emerald-600 px-5 py-3 text-sm font-black uppercase tracking-[0.18em] text-white shadow-[0_18px_38px_rgba(5,150,105,0.32)] hover:bg-emerald-500"
                >
                    Leave
                </button>
            </div>
        </div>
    );
}
