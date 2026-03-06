import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSocket } from '../contexts/SocketContext';
import { useGameState } from '../contexts/GameContext';
import { getApiUrl } from '../config';

export default function Lobby() {
    const [isQueuing, setIsQueuing] = useState(false);
    const navigate = useNavigate();
    const { isConnected, connect } = useSocket();
    const { gameState } = useGameState();

    useEffect(() => {
        // Attempt Auto-connect if token exists
        const token = localStorage.getItem('fh_token');
        if (token && !isConnected) {
            connect(token);
        }

        // Auto redirect to game room if server pushes a game state down the pipe
        if (gameState && gameState.matchId) {
            navigate(`/game/${gameState.matchId}`);
        }
    }, [isConnected, gameState, navigate, connect]);

    const joinQueue = async () => {
        const token = localStorage.getItem('fh_token');
        if (!token) return navigate('/');

        setIsQueuing(true);
        try {
            const res = await fetch(getApiUrl('/api/v1/matchmaking/join'), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({ ruleset: 'hometown' })
            });

            if (!res.ok) {
                setIsQueuing(false);
                alert("Failed to join queue");
            }
        } catch (e) {
            setIsQueuing(false);
            alert("Error contacting matchmaker");
        }
    };

    return (
        <div className="flex flex-col items-center justify-center min-h-[80vh]">
            <h2 className="text-4xl front-bold mb-4 text-white">Matchmaking Lobby</h2>
            <p className="text-gray-400 mb-8 max-w-lg text-center">
                Socket Status: {isConnected ? <span className="text-green-400">Connected</span> : <span className="text-red-400">Disconnected</span>}
            </p>

            {isQueuing ? (
                <div className="flex flex-col items-center animate-pulse">
                    <div className="w-16 h-16 border-4 border-green-500 border-t-transparent rounded-full animate-spin mb-4" />
                    <span className="text-xl text-green-300">Searching for players (Redis Queue)...</span>
                </div>
            ) : (
                <button
                    onClick={joinQueue}
                    disabled={!isConnected}
                    className="bg-green-600 hover:bg-green-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-bold py-4 px-12 rounded-full text-2xl shadow-lg transition-all transform hover:scale-105"
                >
                    Find Match (Hometown Rules)
                </button>
            )}
        </div>
    );
}
