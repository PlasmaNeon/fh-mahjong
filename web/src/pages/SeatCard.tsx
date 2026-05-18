// @ts-nocheck
import { game } from '../proto/game';

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
        <div className="rounded-2xl border border-emerald-300/16 bg-slate-950/70 p-5">
            <div className="flex items-center justify-between text-[11px] uppercase tracking-[0.18em] text-emerald-200/70">
                <span>Seat {seatIndex + 1} · {SEAT_LABEL[seatIndex]}</span>
                {isHumanHost && <span className="rounded-full border border-amber-300/40 px-2 py-0.5 text-amber-200">Host</span>}
            </div>

            <div className="mt-3 text-base font-semibold text-emerald-100">
                {seat.kind === 'human' && <>{seat.username || `Player ${seat.userId ?? ''}`}</>}
                {seat.kind === 'bot' && <>AI · Heuristic</>}
                {(seat.kind === 'empty' || !seat.kind) && <span className="text-slate-400">Waiting for player…</span>}
            </div>

            {canEdit && (seat.kind === 'empty' || !seat.kind) && (
                <div className="mt-3 flex flex-wrap gap-2">
                    {DIFFICULTY_OPTIONS.map(opt => (
                        <button
                            key={opt.value}
                            type="button"
                            onClick={() => onAssignBot(seatIndex, opt.value)}
                            className="rounded-full border border-cyan-300/30 bg-cyan-900/40 px-3 py-1 text-xs uppercase tracking-[0.16em] text-cyan-100 hover:bg-cyan-800/50"
                        >
                            Add AI · {opt.label}
                        </button>
                    ))}
                </div>
            )}

            {canEdit && seat.kind === 'bot' && (
                <div className="mt-3 flex flex-wrap gap-2">
                    <button
                        type="button"
                        onClick={() => onClearSeat(seatIndex)}
                        className="rounded-full border border-rose-300/30 bg-rose-900/40 px-3 py-1 text-xs uppercase tracking-[0.16em] text-rose-100 hover:bg-rose-800/50"
                    >
                        Remove AI
                    </button>
                </div>
            )}

            {isHost && !canEdit && (
                <div className="mt-3 text-[11px] uppercase tracking-[0.16em] text-slate-500">Only the host can change seats.</div>
            )}
        </div>
    );
}
