// @ts-nocheck
import { game } from '../../proto/game';
import { Button } from '../../theme';
import { useI18n } from '../../i18n/I18nContext';
import { WIND_KANJI, windI18nKey } from '../../utils/winds';
import { rlSeatLabel, type RLAgentInfo } from './rlAgents';

type SeatConfig = game.ISeatConfig;
type Difficulty = game.Difficulty;

export interface SeatCardProps {
    seatIndex: number;
    seat: SeatConfig;
    isHost: boolean;
    canEdit: boolean;
    hostUserId: number;
    rlAgents?: RLAgentInfo[];
    onAssignBot: (seat: number, difficulty: Difficulty, rlAgent?: string) => void;
    onClearSeat: (seat: number) => void;
}


export default function SeatCard(props: SeatCardProps) {
    const { t } = useI18n();
    const { seatIndex, seat, isHost, canEdit, hostUserId, rlAgents = [], onAssignBot, onClearSeat } = props;

    const isHumanHost = seat.kind === 'human' && Number(seat.userId ?? 0) === hostUserId;

    return (
        <div className={`ldg-meld seat-card seat-card--${seat.kind || 'empty'}`}>
            <div className="seat-card__wind" aria-hidden="true">{WIND_KANJI[seatIndex + 1]}</div>
            <div className="ldg-meld__head">
                <div>
                    <div className="ldg-meld__meta">{t('room.seatWind', { seat: seatIndex + 1, wind: t(windI18nKey(seatIndex + 1)) })}</div>
                    <div className="ldg-meld__title" style={{ marginTop: 4 }}>
                        {seat.kind === 'human' && <>{seat.username || `Player ${seat.userId ?? ''}`}</>}
                        {seat.kind === 'bot' && <>AI · {Number(seat.difficulty) === game.Difficulty.DIFFICULTY_RL
                            ? (rlSeatLabel(seat.rlAgent, rlAgents) ?? t('room.rlAgent'))
                            : t('room.heuristic')}</>}
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
                        {/* Heuristic is always available. Each RL agent from GET /api/v1/config
                            is listed so hosts know it exists, disabled while its model server is
                            unreachable (the room page re-polls, so entries enable live). */}
                        <button onClick={() => onAssignBot(seatIndex, game.Difficulty.DIFFICULTY_HEURISTIC)}>
                            {t('room.heuristic')}
                        </button>
                        {rlAgents.map(agent => (
                            <button key={agent.id} disabled={!agent.available}
                                onClick={() => onAssignBot(seatIndex, game.Difficulty.DIFFICULTY_RL, agent.id)}>
                                {agent.label}{agent.available ? '' : ` · ${t('room.offlineShort')}`}
                            </button>
                        ))}
                        {rlAgents.length === 0 && (
                            <button disabled>{t('room.rlAgent')} · {t('room.offlineShort')}</button>
                        )}
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
