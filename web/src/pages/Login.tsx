import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSocket } from '../contexts/SocketContext';
import { getApiUrl } from '../config';
import { Page, Shell, Card, PageHeader, Section, ToolsRow, Button, TextLink, Field, Note } from '../theme';

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
        <Page>
            <Shell>
                <Card>
                    <PageHeader
                        title="Login"
                        subtitle="登录 · 奉化麻将"
                        nav={<>
                            <TextLink to="/">Home</TextLink>
                            <TextLink to="/room/new">Private room →</TextLink>
                        </>}
                    />

                    <Section title="Account access" subtitle="Login for matchmaking, or register a new account.">
                        <Field label="Username" value={username} onChange={e => setUsername(e.target.value)} autoComplete="username" />
                        <Field label="Password" type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete="current-password" style={{ marginTop: '0.85rem' }} />

                        {error && <Note tone="error">{error}</Note>}

                        <ToolsRow>
                            <Button variant="primary" onClick={() => handleAuth(true)}>Login</Button>
                            <Button onClick={() => handleAuth(false)}>Register</Button>
                        </ToolsRow>
                    </Section>
                </Card>
            </Shell>
        </Page>
    );
}
