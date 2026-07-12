// @ts-nocheck
import { game } from '../../proto/game';
import { Button } from '../../theme';

type SeatConfig = game.ISeatConfig;
type Difficulty = game.Difficulty;

export interface SeatCardProps {
    seatIndex: number;
    seat: SeatConfig;
    isHost: boolean;
    canEdit: boolean;
    hostUserId: number;
    rlAgentAvailable?: boolean;
    onAssignBot: (seat: number, difficulty: Difficulty) => void;
    onClearSeat: (seat: number) => void;
}

const DIFFICULTY_LABELS: Record<number, string> = {
    [game.Difficulty.DIFFICULTY_HEURISTIC]: 'Heuristic',
    [game.Difficulty.DIFFICULTY_RL]: 'RL Agent',
};

function difficultyLabel(difficulty: Difficulty | number | null | undefined): string {
    return DIFFICULTY_LABELS[Number(difficulty ?? 0)] ?? 'Heuristic';
}

// Heuristic is always available. The RL Agent option is always shown so hosts
// know it exists, but it stays disabled until the trained policy endpoint is
// reachable (surfaced via GET /api/v1/config, polled by the room page so it
// enables/disables live as the model server comes up or goes down).
function difficultyOptions(rlAgentAvailable: boolean): Array<{ value: Difficulty; label: string; disabled: boolean }> {
    return [
        { value: game.Difficulty.DIFFICULTY_HEURISTIC, label: 'Heuristic', disabled: false },
        { value: game.Difficulty.DIFFICULTY_RL, label: 'RL Agent', disabled: !rlAgentAvailable },
    ];
}

const SEAT_LABEL = ['East', 'South', 'West', 'North'];
const SEAT_WIND = ['東', '南', '西', '北'];

export default function SeatCard(props: SeatCardProps) {
    const { seatIndex, seat, isHost, canEdit, hostUserId, rlAgentAvailable = false, onAssignBot, onClearSeat } = props;

    const isHumanHost = seat.kind === 'human' && Number(seat.userId ?? 0) === hostUserId;

    return (
        <div className={`ldg-meld seat-card seat-card--${seat.kind || 'empty'}`}>
            <div className="seat-card__wind" aria-hidden="true">{SEAT_WIND[seatIndex]}</div>
            <div className="ldg-meld__head">
                <div>
                    <div className="ldg-meld__meta">Seat {seatIndex + 1} · {SEAT_LABEL[seatIndex]} wind</div>
                    <div className="ldg-meld__title" style={{ marginTop: 4 }}>
                        {seat.kind === 'human' && <>{seat.username || `Player ${seat.userId ?? ''}`}</>}
                        {seat.kind === 'bot' && <>AI · {difficultyLabel(seat.difficulty)}</>}
                        {(seat.kind === 'empty' || !seat.kind) && (
                            <span style={{ color: 'var(--ink-3)', fontWeight: 400 }}>Waiting for player…</span>
                        )}
                    </div>
                </div>
                {isHumanHost && <span className="ldg-chip ldg-chip--active">Host</span>}
            </div>

            {canEdit && (seat.kind === 'empty' || !seat.kind) && (
                <div className="ldg-meld__actions">
                    <Button onClick={() => onAssignBot(seatIndex, game.Difficulty.DIFFICULTY_HEURISTIC)}>Add AI</Button>
                    <details className="seat-card__advanced">
                        <summary>AI type</summary>
                        {difficultyOptions(rlAgentAvailable).map(opt => (
                            <button key={opt.value} disabled={opt.disabled} onClick={() => onAssignBot(seatIndex, opt.value)}>
                                {opt.label}{opt.disabled ? ' · offline' : ''}
                            </button>
                        ))}
                    </details>
                </div>
            )}

            {canEdit && seat.kind === 'bot' && (
                <div className="ldg-meld__actions">
                    <Button variant="danger" onClick={() => onClearSeat(seatIndex)}>Remove AI</Button>
                </div>
            )}
        </div>
    );
}
