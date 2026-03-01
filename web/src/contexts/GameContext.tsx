import React, { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { useSocket } from './SocketContext';
import { GameState } from '../proto/game';

interface GameContextType {
    gameState: GameState | null;
    mySeatId: number | null;
}

const GameContext = createContext<GameContextType>({
    gameState: null,
    mySeatId: null,
});

export const useGameState = () => useContext(GameContext);

export const GameProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
    const { socket, isConnected } = useSocket();
    const [gameState, setGameState] = useState<GameState | null>(null);
    const [mySeatId, setMySeatId] = useState<number | null>(null);

    useEffect(() => {
        if (!socket || !isConnected) return;

        const handleMessage = async (event: MessageEvent) => {
            try {
                if (typeof event.data === 'string') {
                    const data = JSON.parse(event.data);
                    if (data.type === 'seat_assignment') {
                        setMySeatId(data.seat);
                    }
                    return;
                }

                let buffer: Uint8Array;

                // Handle Blob or ArrayBuffer
                if (event.data instanceof Blob) {
                    const arrayBuf = await event.data.arrayBuffer();
                    buffer = new Uint8Array(arrayBuf);
                } else {
                    buffer = new Uint8Array(event.data);
                }

                // Deserialize the Protobuf via ts-proto!
                const decodedState = GameState.decode(buffer);
                console.log("New Game State Received:", decodedState);
                setGameState(decodedState);
            } catch (err) {
                console.error("Failed to decode GameState protobuf:", err);
            }
        };

        socket.addEventListener('message', handleMessage);

        return () => {
            socket.removeEventListener('message', handleMessage);
        };
    }, [socket, isConnected]);

    return (
        <GameContext.Provider value={{ gameState, mySeatId }}>
            {children}
        </GameContext.Provider>
    );
};
