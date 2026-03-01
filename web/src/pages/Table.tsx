import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useSocket } from '../contexts/SocketContext';
import { useGameState } from '../contexts/GameContext';

export default function Table() {
    const { tableId } = useParams();
    const [username, setUsername] = useState('');
    const [isQueuing, setIsQueuing] = useState(false);
    const [error, setError] = useState('');
    const [isReady, setIsReady] = useState(false);
    const [lobbyMsg, setLobbyMsg] = useState('');

    const navigate = useNavigate();
    const { isConnected, connect, socket } = useSocket();
    const { gameState } = useGameState();

    // If a game state broadcasts, drop us into the active game route.
    useEffect(() => {
        if (gameState && gameState.matchId) {
            navigate(`/game/${gameState.matchId}`);
        }
    }, [gameState, navigate]);

    // Listen for non-binary Lobby Announcements directly from the socket
    useEffect(() => {
        if (!socket || !isConnected) return;

        const handleLobbyMessage = (e: MessageEvent) => {
            if (typeof e.data === 'string') {
                try {
                    const data = JSON.parse(e.data);
                    if (data.type === 'lobby_update' && data.table === tableId) {
                        setLobbyMsg(data.message);
                    }
                } catch (err) {
                    console.error("Lobby parse error", err);
                }
            }
        };

        socket.addEventListener('message', handleLobbyMessage);
        return () => socket.removeEventListener('message', handleLobbyMessage);
    }, [socket, isConnected, tableId]);

    const [guestToken, setGuestToken] = useState('');

    useEffect(() => {
        const storedToken = sessionStorage.getItem('mahjong_token');
        if (storedToken && !isConnected) {
            setGuestToken(storedToken);
            connect(storedToken);
            setIsReady(true);
        }
    }, [connect, isConnected]);

    const handleGuestJoin = async () => {
        if (!username.trim() || !tableId) return;
        setIsQueuing(true);
        try {
            const authRes = await fetch('/api/v1/auth/guest', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username })
            });
            const authData = await authRes.json();
            if (!authRes.ok) throw new Error(authData.error || 'Guest auth failed');

            setGuestToken(authData.token);
            sessionStorage.setItem('mahjong_token', authData.token);
            connect(authData.token);
            setIsReady(true);
            setIsQueuing(false);
        } catch (err: any) {
            setError(err.message);
            setIsQueuing(false);
        }
    };

    const handleSetReady = async () => {
        setIsQueuing(true);
        try {
            const res = await fetch('/api/v1/matchmaking/private', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${guestToken}`
                },
                body: JSON.stringify({ tableId })
            });

            if (!res.ok) throw new Error("Failed to join private table");
        } catch (err: any) {
            setError(err.message);
            setIsQueuing(false);
        }
    };

    return (
        <div className="flex flex-col items-center justify-center min-h-[80vh]">
            <div className="bg-gray-800 p-8 rounded-xl shadow-2xl w-full max-w-sm border border-gray-700">
                <h1 className="text-2xl font-bold mb-4 text-green-400 text-center">Private Table</h1>
                <h2 className="text-sm font-mono text-gray-500 text-center mb-8">{tableId}</h2>

                {error && <div className="bg-red-900/50 border border-red-500 text-red-200 px-4 py-2 rounded mb-4 text-sm">{error}</div>}

                {!isReady ? (
                    <>
                        <input
                            autoFocus
                            className="w-full bg-gray-900 text-white border border-gray-600 rounded px-4 py-2 mb-6 focus:outline-none focus:border-green-500"
                            placeholder="Enter Temp Username"
                            value={username}
                            onChange={e => setUsername(e.target.value)}
                            onKeyDown={e => e.key === 'Enter' && handleGuestJoin()}
                        />
                        <button
                            className="w-full bg-blue-600 hover:bg-blue-500 text-white font-bold py-2 rounded disabled:opacity-50"
                            onClick={handleGuestJoin}
                            disabled={isQueuing}
                        >
                            Set Name & Continue
                        </button>
                    </>
                ) : (
                    <div className="flex flex-col items-center">
                        <span className="text-xl text-green-300 mb-4">{isConnected ? 'Connected!' : 'Connecting...'}</span>
                        {isQueuing ? (
                            <div className="flex flex-col items-center animate-pulse">
                                <span className="text-xl text-green-300 mb-4">{lobbyMsg || 'Waiting for 4 players...'}</span>
                                <span className="text-sm text-gray-400 mb-6">Hang tight! Game starts automatically.</span>
                                <div className="w-12 h-12 border-4 border-green-500 border-t-transparent rounded-full animate-spin" />
                            </div>
                        ) : (
                            <button
                                onClick={handleSetReady}
                                disabled={!isConnected}
                                className="w-full bg-green-600 hover:bg-green-500 disabled:opacity-50 text-white font-bold py-3 rounded text-lg shadow-lg transition-transform transform hover:scale-105"
                            >
                                I'm Ready!
                            </button>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}
