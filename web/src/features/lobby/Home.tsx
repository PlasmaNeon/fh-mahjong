import { Link, useLocation, type LinkProps } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import type { AuthRouteState } from '../auth/authModal'

export default function Home() {
    const { status, user } = useAuth()
    const location = useLocation()
    const profileState: AuthRouteState | undefined = user ? undefined : { backgroundLocation: location, optionalAuth: true }
    return (
        <main className="ledger-page">
            <div className="club-home">
                <div className="club-home__brand">奉化麻将 · Rainy Mahjong Club</div>
                <nav className="club-home__menu" aria-label="Club menu">
                    <div className="club-home__compass" aria-hidden="true"><span>東</span></div>
                    <div className="club-home__links">
                        <HomeLink to="/play" title="Play" mark="ENTER" primary />
                        <HomeLink to="/tools/calc" title="Table Tools" mark="TOOLS" />
                        <HomeLink to="/replay" title="Paipu Replay" mark="PAIPU" />
                        <HomeLink to={user ? '/account' : `/login?returnTo=${encodeURIComponent('/account')}`} state={profileState} title="Profile" mark={status === 'loading' ? '…' : 'YOU'} />
                    </div>
                </nav>
            </div>
        </main>
    )
}

function HomeLink({ to, state, title, mark, primary = false }: { to: string; state?: LinkProps['state']; title: string; mark: string; primary?: boolean }) {
    return <Link className={`club-home__link${primary ? ' club-home__link--primary' : ''}`} to={to} state={state}><strong>{title}</strong><span className="club-home__link-mark">{mark} →</span></Link>
}
