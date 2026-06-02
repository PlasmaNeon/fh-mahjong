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
