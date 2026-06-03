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

// The RL Agent option is only offered when the server has a trained policy
// endpoint configured (surfaced via GET /api/v1/config). Heuristic is always
// available.
function difficultyOptions(rlAgentAvailable: boolean): Array<{ value: Difficulty; label: string }> {
    const options: Array<{ value: Difficulty; label: string }> = [
        { value: game.Difficulty.DIFFICULTY_HEURISTIC, label: 'Heuristic' },
    ];
    if (rlAgentAvailable) {
        options.push({ value: game.Difficulty.DIFFICULTY_RL, label: 'RL Agent' });
    }
    return options;
}

const SEAT_LABEL = ['East', 'South', 'West', 'North'];

export default function SeatCard(props: SeatCardProps) {
    const { seatIndex, seat, isHost, canEdit, hostUserId, rlAgentAvailable = false, onAssignBot, onClearSeat } = props;

    const isHumanHost = seat.kind === 'human' && Number(seat.userId ?? 0) === hostUserId;

    return (
        <div className="ldg-meld">
            <div className="ldg-meld__head">
                <div>
                    <div className="ldg-meld__meta">Seat {seatIndex + 1} · {SEAT_LABEL[seatIndex]}</div>
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
                    {difficultyOptions(rlAgentAvailable).map(opt => (
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
