import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useSocket } from '../contexts/SocketContext';
import { getApiUrl } from '../config';
import './ledger-theme.css';

export default function Login() {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const navigate = useNavigate();
    const { connect } = useSocket();

    const handleAuth = async (isLogin: boolean) => {
        try {
            const endpoint = isLogin ? getApiUrl('/api/v1/auth/login') : getApiUrl('/api/v1/auth/register');
            const res = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password }),
            });

            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Authentication failed');

            if (!isLogin) {
                alert('Registration successful! Please login.');
                return;
            }

            localStorage.setItem('fh_token', data.token);
            connect(data.token);
            navigate('/play');
        } catch (err: any) {
            setError(err.message);
        }
    };

    return (
        <div className="ledger-page">
            <div className="ledger-shell">
                <article className="ldg-page">
                    <div className="ldg-page-head">
                        <div>
                            <h1 className="ldg-page-head__title">
                                Login
                                <small>登录 · 奉化麻将</small>
                            </h1>
                        </div>
                        <div className="ldg-page-head__nav">
                            <Link to="/" className="ldg-link">Home</Link>
                            <Link to="/room/new" className="ldg-link">Private room →</Link>
                        </div>
                    </div>

                    <section className="ldg-section">
                        <div className="ldg-section-row">
                            <h2 className="ldg-section-title">
                                Account access
                                <small>Login for matchmaking, or register a new account.</small>
                            </h2>
                        </div>

                        <div className="ldg-field">
                            <label className="ldg-field__label">Username</label>
                            <input
                                className="ldg-input"
                                value={username}
                                onChange={e => setUsername(e.target.value)}
                                autoComplete="username"
                            />
                        </div>
                        <div className="ldg-field" style={{ marginTop: '0.85rem' }}>
                            <label className="ldg-field__label">Password</label>
                            <input
                                type="password"
                                className="ldg-input"
                                value={password}
                                onChange={e => setPassword(e.target.value)}
                                autoComplete="current-password"
                            />
                        </div>

                        {error && <p className="ldg-note ldg-note--err">{error}</p>}

                        <div className="ldg-tools-row" style={{ marginTop: '1.1rem' }}>
                            <button className="ldg-btn ldg-btn--primary" onClick={() => handleAuth(true)}>Login</button>
                            <button className="ldg-btn" onClick={() => handleAuth(false)}>Register</button>
                        </div>
                    </section>
                </article>
            </div>
        </div>
    );
}
