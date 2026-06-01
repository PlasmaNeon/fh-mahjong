import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useSocket } from '../contexts/SocketContext';
import { useGameState } from '../contexts/GameContext';
import { getApiUrl } from '../config';
import './ledger-theme.css';

export default function Lobby() {
    const [isQueuing, setIsQueuing] = useState(false);
    const [error, setError] = useState('');
    const navigate = useNavigate();
    const { isConnected, connect } = useSocket();
    const { gameState } = useGameState();

    useEffect(() => {
        const token = localStorage.getItem('fh_token');
        if (token && !isConnected) {
            connect(token);
        }

        if (gameState && gameState.matchId) {
            navigate(`/match/${gameState.matchId}`);
        }
    }, [isConnected, gameState, navigate, connect]);

    const joinQueue = async (ruleset: 'hometown' | 'chongci-fh' = 'hometown') => {
        const token = localStorage.getItem('fh_token');
        if (!token) return navigate('/login');

        setError('');
        setIsQueuing(true);
        try {
            const res = await fetch(getApiUrl('/api/v1/matchmaking/join'), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`,
                },
                body: JSON.stringify({ ruleset }),
            });

            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                throw new Error(data.error || 'Failed to join queue');
            }
        } catch (e: any) {
            setError(e.message || 'Error contacting matchmaker');
            setIsQueuing(false);
        }
    };

    return (
        <div className="ledger-page">
            <div className="ledger-shell">
                <article className="ldg-page">
                    <div className="ldg-page-head">
                        <div>
                            <h1 className="ldg-page-head__title">
                                Play
                                <small>实时匹配 · Hometown rules</small>
                            </h1>
                        </div>
                        <div className="ldg-page-head__nav">
                            <Link to="/" className="ldg-link">Home</Link>
                            <Link to="/room/new" className="ldg-link">Private room →</Link>
                        </div>
                    </div>

                    <section className="ldg-section">
                        <div className="ldg-section-row">
                            <h2 className="ldg-section-title">Matchmaking</h2>
                            <span className="ldg-section-meta">{isConnected ? 'socket ready' : 'socket offline'}</span>
                        </div>

                        {error && <p className="ldg-note ldg-note--err">{error}</p>}

                        {isQueuing ? (
                            <p className="ldg-note">
                                Searching for players… stay on this page; you'll jump into the match
                                automatically once the room is ready.
                            </p>
                        ) : (
                            <div className="ldg-tools-row">
                                <button
                                    className="ldg-btn ldg-btn--primary"
                                    disabled={!isConnected}
                                    onClick={() => joinQueue('hometown')}
                                >
                                    Find Match
                                </button>
                                <button
                                    className="ldg-btn"
                                    disabled={!isConnected}
                                    onClick={() => joinQueue('chongci-fh')}
                                >
                                    Quick Match · Chongci
                                </button>
                                <Link to="/room/new" className="ldg-btn">Private Room</Link>
                            </div>
                        )}
                    </section>
                </article>
            </div>
        </div>
    );
}
