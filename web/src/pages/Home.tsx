import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

// Decode the username from the stored JWT, if present, so the account link
// reflects logged-in state without a network call.
function useStoredUsername(): string | null {
    const [username, setUsername] = useState<string | null>(null)
    useEffect(() => {
        const token = localStorage.getItem('fh_token')
        if (!token) {
            setUsername(null)
            return
        }
        const parts = token.split('.')
        if (parts.length !== 3) {
            setUsername(null)
            return
        }
        try {
            const payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')))
            setUsername(typeof payload.username === 'string' ? payload.username : null)
        } catch {
            setUsername(null)
        }
    }, [])
    return username
}

export default function Home() {
    const username = useStoredUsername()

    return (
        <div className="ledger-page">
            <div className="ledger-shell">
                <article className="ldg-page">
                    <div className="ldg-page-head">
                        <div>
                            <h1 className="ldg-page-head__title">
                                Fenghua Mahjong
                                <small>奉化麻将</small>
                            </h1>
                        </div>
                        <div className="ldg-page-head__nav">
                            <Link to="/login" className="ldg-link">
                                {username ? `Signed in · ${username}` : 'Login / Register'}
                            </Link>
                        </div>
                    </div>

                    <p className="ldg-note" style={{ marginTop: '1.25rem' }}>
                        Jump into a live public match, set up a private room for friends, or open the
                        scoring and shanten tools.
                    </p>

                    <section className="ldg-section">
                        <div className="ldg-section-row">
                            <h2 className="ldg-section-title">
                                Play
                                <small>Live hometown-rules matchmaking</small>
                            </h2>
                        </div>
                        <div className="ldg-tools-row">
                            <Link to="/play" className="ldg-btn ldg-btn--primary">Find Match →</Link>
                        </div>
                    </section>

                    <section className="ldg-section">
                        <div className="ldg-section-row">
                            <h2 className="ldg-section-title">
                                Private Room
                                <small>Play with friends by link</small>
                            </h2>
                        </div>
                        <div className="ldg-tools-row">
                            <Link to="/room/new" className="ldg-btn">Create Private Room →</Link>
                        </div>
                    </section>

                    <section className="ldg-section">
                        <div className="ldg-section-row">
                            <h2 className="ldg-section-title">
                                Tools
                                <small>No login needed</small>
                            </h2>
                        </div>
                        <div className="ldg-tools-row">
                            <Link to="/tools/calc" className="ldg-btn">Scoring Calculator</Link>
                            <Link to="/tools/shanten" className="ldg-btn">Shanten Calculator</Link>
                        </div>
                    </section>
                </article>
            </div>
        </div>
    )
}
