import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { SocketProvider } from './contexts/SocketContext'
import { GameProvider } from './contexts/GameContext'
import Home from './pages/Home'
import Login from './pages/Login'
import Lobby from './pages/Lobby'
import Table from './pages/Table'
import Game from './pages/Game'
import Calc from './pages/Calc'
import Shanten from './pages/Shanten'
import Replay from './pages/Replay'
import CreateRoom from './pages/CreateRoom'

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
