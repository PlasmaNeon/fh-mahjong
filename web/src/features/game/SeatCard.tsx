// @ts-nocheck
import { game } from '../../proto/game';
import { Button } from '../../theme';
import { useI18n } from '../../i18n/I18nContext';
import { WIND_KANJI, windI18nKey } from '../../utils/winds';

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


export default function SeatCard(props: SeatCardProps) {
    const { t } = useI18n();
    const { seatIndex, seat, isHost, canEdit, hostUserId, rlAgentAvailable = false, onAssignBot, onClearSeat } = props;

    const isHumanHost = seat.kind === 'human' && Number(seat.userId ?? 0) === hostUserId;

    return (
        <div className={`ldg-meld seat-card seat-card--${seat.kind || 'empty'}`}>
            <div className="seat-card__wind" aria-hidden="true">{WIND_KANJI[seatIndex + 1]}</div>
            <div className="ldg-meld__head">
                <div>
                    <div className="ldg-meld__meta">{t('room.seatWind', { seat: seatIndex + 1, wind: t(windI18nKey(seatIndex + 1)) })}</div>
                    <div className="ldg-meld__title" style={{ marginTop: 4 }}>
                        {seat.kind === 'human' && <>{seat.username || `Player ${seat.userId ?? ''}`}</>}
                        {seat.kind === 'bot' && <>AI · {t(Number(seat.difficulty) === game.Difficulty.DIFFICULTY_RL ? 'room.rlAgent' : 'room.heuristic')}</>}
                        {(seat.kind === 'empty' || !seat.kind) && (
                            <span style={{ color: 'var(--ink-3)', fontWeight: 400 }}>{t('room.waitingPlayer')}</span>
                        )}
                    </div>
                </div>
                {isHumanHost && <span className="ldg-chip ldg-chip--active">{t('room.host')}</span>}
            </div>

            {canEdit && (seat.kind === 'empty' || !seat.kind) && (
                <div className="ldg-meld__actions">
                    <Button onClick={() => onAssignBot(seatIndex, game.Difficulty.DIFFICULTY_HEURISTIC)}>{t('room.addAI')}</Button>
                    <details className="seat-card__advanced">
                        <summary>{t('room.aiType')}</summary>
                        {difficultyOptions(rlAgentAvailable).map(opt => (
                            <button key={opt.value} disabled={opt.disabled} onClick={() => onAssignBot(seatIndex, opt.value)}>
                                {opt.value === game.Difficulty.DIFFICULTY_RL ? t('room.rlAgent') : t('room.heuristic')}{opt.disabled ? ` · ${t('room.offlineShort')}` : ''}
                            </button>
                        ))}
                    </details>
                </div>
            )}

            {canEdit && seat.kind === 'bot' && (
                <div className="ldg-meld__actions">
                    <Button variant="danger" onClick={() => onClearSeat(seatIndex)}>{t('room.removeAI')}</Button>
                </div>
            )}
        </div>
    );
}
