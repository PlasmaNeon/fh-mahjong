import { Link } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'

export default function Home() {
    const { status, user } = useAuth()
    return (
        <main className="ledger-page">
            <div className="club-home">
                <section>
                    <div className="club-home__brand">奉化麻将 · Rainy Mahjong Club</div>
                    <h1 className="club-home__title">One more hand before the rain stops.</h1>
                    <p className="club-home__lead">A late-night table for Fenghua rules—find a live match, open a private room, or work through a hand at the scoring desk.</p>
                </section>
                <nav className="club-home__menu" aria-label="Club menu">
                    <div className="club-home__compass" aria-hidden="true"><span>東</span></div>
                    <div className="club-home__menu-label">Tonight at the club</div>
                    <div className="club-home__links">
                        <HomeLink to="/play" title="Play" detail="Quick match or a private table" mark="ENTER" primary />
                        <HomeLink to="/tools/calc" title="Table Tools" detail="Scoring and shanten workbench" mark="TOOLS" />
                        <HomeLink to={user ? '/account' : '/login'} title="Profile" detail={status === 'loading' ? 'Checking your club pass…' : status === 'offline' ? 'Club connection unavailable' : user ? `Signed in as ${user.username}` : 'Sign in or create an account'} mark="YOU" />
                    </div>
                </nav>
            </div>
        </main>
    )
}

function HomeLink({ to, title, detail, mark, primary = false }: { to: string; title: string; detail: string; mark: string; primary?: boolean }) {
    return <Link className={`club-home__link${primary ? ' club-home__link--primary' : ''}`} to={to}><span><strong>{title}</strong><small>{detail}</small></span><span className="club-home__link-mark">{mark} →</span></Link>
}
