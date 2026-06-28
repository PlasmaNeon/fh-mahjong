import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { SocketProvider } from './contexts/SocketContext'
import { GameProvider } from './contexts/GameContext'
import Home from './features/lobby/Home'
import Login from './features/auth/Login'
import Lobby from './features/lobby/Lobby'
import Table from './pages/Table'
import Game from './pages/Game'
import Calc from './features/calc/Calc'
import Shanten from './features/shanten/Shanten'
import Replay from './pages/Replay'
import CreateRoom from './features/lobby/CreateRoom'

function App() {
    return (
        <SocketProvider>
            <GameProvider>
                <BrowserRouter>
                    <div className="min-h-screen bg-gray-900 text-white font-sans w-full">
                        <Routes>
                            <Route path="/" element={<Home />} />
                            <Route path="/login" element={<Login />} />
                            <Route path="/play" element={<Lobby />} />
                            <Route path="/room/new" element={<CreateRoom />} />
                            <Route path="/room/:roomId" element={<Table />} />
                            <Route path="/match/:matchId" element={<Game />} />
                            <Route path="/replay/:matchId" element={<Replay />} />
                            <Route path="/tools/calc" element={<Calc />} />
                            <Route path="/tools/shanten" element={<Shanten />} />
                            <Route path="*" element={<Navigate to="/" />} />
                        </Routes>
                    </div>
                </BrowserRouter>
            </GameProvider>
        </SocketProvider>
    )
}

export default App
