import { BrowserRouter, Routes, Route, Navigate, useLocation, useParams } from 'react-router-dom'
import { SocketProvider } from './contexts/SocketContext'
import { AuthProvider } from './contexts/AuthContext'
import { GameProvider } from './contexts/GameContext'
import Home from './features/lobby/Home'
import Login from './features/auth/Login'
import Lobby from './features/lobby/Lobby'
import PrivateRoom from './features/game/PrivateRoom'
import Game from './features/game/Game'
import Calc from './features/calc/Calc'
import Shanten from './features/shanten/Shanten'
import Replay from './features/replay/Replay'
import ReplayLibrary from './features/replay/ReplayLibrary'
import CreateRoom from './features/lobby/CreateRoom'
import Account from './features/auth/Account'
import TableSample from './features/dev/TableSample'
import RoundResultDemo from './features/dev/RoundResultDemo'
import type { AuthRouteState } from './features/auth/authRouteState'

// Keying the waiting room by its room id forces a fresh component instance per
// room, so route-local seats, requests, and reconnect state never carry over
// when navigating between different room links.
function PrivateRoomRoute() {
    const { roomId } = useParams()
    return <PrivateRoom key={roomId} />
}

function LoginBackdrop() {
    return <main className="ledger-page auth-login-stage"><div className="auth-login-stage__compass" aria-hidden="true"><span>東</span></div></main>
}

function AppRoutes() {
    const location = useLocation()
    const authState = location.state as AuthRouteState | null
    const showLogin = location.pathname === '/login'
    const backgroundLocation = showLogin ? authState?.backgroundLocation : undefined

    return <div className="app-root">
        <div className="app-view" aria-hidden={showLogin || undefined} inert={showLogin || undefined}>
            <Routes location={backgroundLocation ?? location}>
                <Route path="/" element={<Home />} />
                <Route path="/login" element={<LoginBackdrop />} />
                <Route path="/play" element={<Lobby />} />
                <Route path="/account" element={<Account />} />
                <Route path="/room/new" element={<CreateRoom />} />
                <Route path="/room/:roomId" element={<PrivateRoomRoute />} />
                <Route path="/match/:matchId" element={<Game />} />
                <Route path="/replay" element={<ReplayLibrary />} />
                <Route path="/replay/:matchId" element={<Replay />} />
                <Route path="/tools/calc" element={<Calc />} />
                <Route path="/tools/shanten" element={<Shanten />} />
                <Route path="/tools" element={<Navigate to="/tools/calc" replace />} />
                <Route path="/tools/table-sample" element={<TableSample />} />
                <Route path="/tools/round-result" element={<RoundResultDemo />} />
                <Route path="*" element={<Navigate to="/" />} />
            </Routes>
        </div>
        {showLogin && <Login />}
    </div>
}

function App() {
    return (
        <AuthProvider>
            <SocketProvider>
                <GameProvider>
                    <BrowserRouter>
                        <AppRoutes />
                    </BrowserRouter>
                </GameProvider>
            </SocketProvider>
        </AuthProvider>
    )
}

export default App
