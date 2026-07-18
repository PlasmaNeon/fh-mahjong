// @ts-nocheck
import { useNavigate } from 'react-router-dom';
import { game } from '../../proto/game';
import { GameDialog } from '../../theme';
import { useI18n } from '../../i18n/I18nContext';

type Props = {
    state: game.IGameState;
    seatNames: (string | null)[];   // length 4; null for AI seats
    matchId?: string;               // enables the "Watch Replay" action
};

const rankLabel = (rank: number) => {
    if (rank === 1) return '1st';
    if (rank === 2) return '2nd';
    if (rank === 3) return '3rd';
    return `${rank}th`;
};

export default function MatchEndOverlay({ state, seatNames, matchId }: Props) {
    const navigate = useNavigate();
    const { t, shortLanguage } = useI18n();
    const result = state.matchEndResult;
    if (!result || !result.standings) return null;

    return (
        <GameDialog
            eyebrow={t('game.finalHand', { hand: Number(result.finalHandNum ?? 0) })}
            title={t(result.reason === 'bust' ? 'game.matchOverBust' : result.reason === 'hand_cap' ? 'game.matchOverCap' : 'game.matchOver')}
            tone="win"
            actions={<>
                {matchId && <button onClick={() => navigate(`/replay/${matchId}`)} className="ldg-btn">{t('game.watchReplay')}</button>}
                <button onClick={() => navigate('/')} className="ldg-btn ldg-btn--primary">{t('game.backClub')}</button>
            </>}
        >
                <div className="match-standings">
                    <table>
                        <thead>
                            <tr>
                                <th>{t('game.rank')}</th>
                                <th>{t('game.player')}</th>
                                <th>{t('game.score')}</th>
                                <th>Δ</th>
                            </tr>
                        </thead>
                        <tbody>
                            {result.standings.map(s => {
                                const seat = Number(s.seat ?? 0);
                                const name = seatNames[seat] ?? `Seat ${seat}`;
                                const net = Number(s.netChange ?? 0);
                                return (
                                    <tr key={seat}>
                                        <td className="match-standings__rank">{shortLanguage === 'zh' ? `第 ${Number(s.rank ?? 0)} 名` : rankLabel(Number(s.rank ?? 0))}</td>
                                        <td>{name}</td>
                                        <td>{Number(s.finalScore ?? 0)}</td>
                                        <td className={net >= 0 ? 'match-standings__gain' : 'match-standings__loss'}>
                                            {net >= 0 ? `+${net}` : `${net}`}
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>

        </GameDialog>
    );
}
