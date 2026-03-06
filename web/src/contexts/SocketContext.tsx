import React, { createContext, useContext, useState, ReactNode } from 'react';
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

    const connect = (token: string) => {
        if (socket) return;

        const wsUrl = `${getWebSocketUrl('/api/v1/ws')}?token=${token}`;

        const ws = new WebSocket(wsUrl);
        ws.binaryType = 'arraybuffer'; // We receive our StateDelta Protobufs as binary arrays!

        ws.onopen = () => {
            console.log('WebSocket Connected');
            setIsConnected(true);
        };

        ws.onclose = () => {
            console.log('WebSocket Disconnected');
            setIsConnected(false);
            setSocket(null);
        };

        ws.onerror = (error) => {
            console.error('WebSocket Error:', error);
        };

        setSocket(ws);
    };

    const disconnect = () => {
        if (socket) {
            socket.close();
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
