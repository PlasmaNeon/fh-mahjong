import React, { createContext, useContext, useState, useRef, ReactNode } from 'react';
import { getWebSocketUrl } from '../config';

interface SocketContextType {
    socket: WebSocket | null;
    isConnected: boolean;
    connect: (token: string) => void;
    disconnect: () => void;
}

const SocketContext = createContext<SocketContextType>({
    socket: null,
    isConnected: false,
    connect: () => { },
    disconnect: () => { },
});

export const useSocket = () => useContext(SocketContext);

export const SocketProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
    const [socket, setSocket] = useState<WebSocket | null>(null);
    const [isConnected, setIsConnected] = useState(false);
    // Refs mirror the live socket + the token it was opened with, so connect()
    // can compare against them without depending on a re-render.
    const socketRef = useRef<WebSocket | null>(null);
    const tokenRef = useRef<string | null>(null);

    const connect = (token: string) => {
        // Already connected with this exact identity → idempotent no-op.
        if (socketRef.current && tokenRef.current === token) return;

        // A different token means a different identity/room (e.g. the user
        // opened another private-room link). Tear down the previous socket so
        // the new room gets its own live connection instead of silently reusing
        // the old one — otherwise every new room shares the first room's socket
        // (and game state), which made distinct links all open the same game.
        if (socketRef.current) {
            const stale = socketRef.current;
            stale.onclose = null; // its handler would clobber the new socket's state
            stale.close();
            socketRef.current = null;
            tokenRef.current = null;
        }

        const wsUrl = `${getWebSocketUrl('/api/v1/ws')}?token=${token}`;

        const ws = new WebSocket(wsUrl);
        ws.binaryType = 'arraybuffer'; // We receive our StateDelta Protobufs as binary arrays!
        socketRef.current = ws;
        tokenRef.current = token;
        setIsConnected(false);

        ws.onopen = () => {
            // Ignore an open that belongs to a socket we've already replaced.
            if (socketRef.current !== ws) return;
            console.log('WebSocket Connected');
            setIsConnected(true);
        };

        ws.onclose = () => {
            // Ignore a close that belongs to a socket we've already replaced.
            if (socketRef.current !== ws) return;
            console.log('WebSocket Disconnected');
            socketRef.current = null;
            tokenRef.current = null;
            setIsConnected(false);
            setSocket(null);
        };

        ws.onerror = (error) => {
            console.error('WebSocket Error:', error);
        };

        setSocket(ws);
    };

    const disconnect = () => {
        const ws = socketRef.current;
        if (ws) {
            socketRef.current = null;
            tokenRef.current = null;
            ws.close();
            setSocket(null);
            setIsConnected(false);
        }
    };

    return (
        <SocketContext.Provider value={{ socket, isConnected, connect, disconnect }}>
            {children}
        </SocketContext.Provider>
    );
};
