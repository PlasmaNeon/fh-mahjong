import { BrowserRouter, Routes, Route, Navigate, useParams } from 'react-router-dom'
import { SocketProvider } from './contexts/SocketContext'
import { GameProvider } from './contexts/GameContext'
import Home from './features/lobby/Home'
import Login from './features/auth/Login'
import Lobby from './features/lobby/Lobby'
import Table from './features/game/Table'
import Game from './features/game/Game'
import Calc from './features/calc/Calc'
import Shanten from './features/shanten/Shanten'
import Replay from './features/replay/Replay'
import CreateRoom from './features/lobby/CreateRoom'
import Account from './features/auth/Account'
import TableSample from './features/dev/TableSample'

// Keying the waiting room by its room id forces a fresh component instance per
// room, so route-local state (token, name, seats, left-marker) never carries
// over when navigating between different room links.
function TableRoute() {
    const { roomId } = useParams()
    return <Table key={roomId} />
}

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
                            <Route path="/account" element={<Account />} />
                            <Route path="/room/new" element={<CreateRoom />} />
                            <Route path="/room/:roomId" element={<TableRoute />} />
                            <Route path="/match/:matchId" element={<Game />} />
                            <Route path="/replay/:matchId" element={<Replay />} />
                            <Route path="/tools/calc" element={<Calc />} />
                            <Route path="/tools/shanten" element={<Shanten />} />
                            <Route path="/tools/table-sample" element={<TableSample />} />
                            <Route path="*" element={<Navigate to="/" />} />
                        </Routes>
                    </div>
                </BrowserRouter>
            </GameProvider>
        </SocketProvider>
    )
}

export default App
