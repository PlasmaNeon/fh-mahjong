// @ts-nocheck
import { useNavigate } from 'react-router-dom';
import { game } from '../../proto/game';
import { GameDialog } from '../../theme';
import { MATCH_LEAVE_CLOSE_CODE, MATCH_LEAVE_REASON, useSocket } from '../../contexts/SocketContext';
import { useGameState } from '../../contexts/GameContext';

type Props = {
    state: game.IGameState;
    seatNames: (string | null)[];   // length 4; null for AI seats
    matchId?: string;               // enables the "Watch Replay" action
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

export default function MatchEndOverlay({ state, seatNames, matchId }: Props) {
    const navigate = useNavigate();
    const { disconnect } = useSocket();
    const { clearGameState } = useGameState();
    const result = state.matchEndResult;
    if (!result || !result.standings) return null;

    return (
        <GameDialog
            eyebrow={`Chongci · Final hand ${Number(result.finalHandNum ?? 0)}`}
            title={reasonLabel(result.reason)}
            tone="win"
            actions={<>
                {matchId && <button onClick={() => navigate(`/replay/${matchId}`)} className="ldg-btn">Watch replay</button>}
                <button onClick={() => {
                    clearGameState();
                    disconnect(MATCH_LEAVE_CLOSE_CODE, MATCH_LEAVE_REASON);
                    navigate('/');
                }} className="ldg-btn ldg-btn--primary">Back to club</button>
            </>}
        >
                <div className="match-standings">
                    <table>
                        <thead>
                            <tr>
                                <th>Rank</th>
                                <th>Player</th>
                                <th>Score</th>
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
                                        <td className="match-standings__rank">{rankLabel(Number(s.rank ?? 0))}</td>
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
