import React, { createContext, useContext, useState, useRef, ReactNode } from 'react';
import { getWebSocketUrl } from '../config';

export const MATCH_LEAVE_CLOSE_CODE = 4000;
export const MATCH_LEAVE_REASON = 'leave_match';

interface SocketContextType {
    socket: WebSocket | null;
    isConnected: boolean;
    connect: () => void;
    disconnect: (code?: number, reason?: string) => void;
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
    const socketRef = useRef<WebSocket | null>(null);

    const connect = () => {
        if (socketRef.current) return;
        const wsUrl = getWebSocketUrl('/api/v1/ws');

        const ws = new WebSocket(wsUrl);
        ws.binaryType = 'arraybuffer'; // We receive our StateDelta Protobufs as binary arrays!
        socketRef.current = ws;
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
            setIsConnected(false);
            setSocket(null);
        };

        ws.onerror = (error) => {
            console.error('WebSocket Error:', error);
        };

        setSocket(ws);
    };

    const disconnect = (code?: number, reason?: string) => {
        const ws = socketRef.current;
        if (ws) {
            socketRef.current = null;
            ws.close(code, reason);
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
