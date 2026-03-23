import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { SocketProvider } from './contexts/SocketContext'
import { GameProvider } from './contexts/GameContext'
import Login from './pages/Login'
import Lobby from './pages/Lobby'
import Table from './pages/Table'
import Game from './pages/Game'
import Calc from './pages/Calc'
import Shanten from './pages/Shanten'
import CreateRoom from './pages/CreateRoom'

function App() {
    return (
        <SocketProvider>
            <GameProvider>
                <BrowserRouter>
                    <div className="min-h-screen bg-gray-900 text-white font-sans w-full">
                        <Routes>
                            <Route path="/" element={<Login />} />
                            <Route path="/lobby" element={<Lobby />} />
                            <Route path="/create-room" element={<CreateRoom />} />
                            <Route path="/calc" element={<Calc />} />
                            <Route path="/shanten" element={<Shanten />} />
                            <Route path="/table/:tableId" element={<Table />} />
                            <Route path="/game/:matchId" element={<Game />} />
                            <Route path="*" element={<Navigate to="/" />} />
                        </Routes>
                    </div>
                </BrowserRouter>
            </GameProvider>
        </SocketProvider>
    )
}

export default App
