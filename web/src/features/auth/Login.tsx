import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSocket } from '../../contexts/SocketContext';
import { getApiUrl } from '../../config';
import { Page, Shell, Card, PageHeader, Section, ToolsRow, Button, TextLink, Field, Note } from '../../theme';

type Mode = 'login' | 'register';

export default function Login() {
    const [mode, setMode] = useState<Mode>('login');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [displayName, setDisplayName] = useState('');
    const [error, setError] = useState('');
    const navigate = useNavigate();
    const { connect } = useSocket();

    const submit = async () => {
        setError('');
        try {
            const isRegister = mode === 'register';
            const endpoint = isRegister ? '/api/v1/auth/register' : '/api/v1/auth/login';
            const body = isRegister ? { email, password, displayName } : { email, password };
            const res = await fetch(getApiUrl(endpoint), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Authentication failed');

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
                        title={mode === 'login' ? 'Sign in' : 'Create account'}
                        subtitle="登录 · 奉化麻将"
                        nav={<>
                            <TextLink to="/">Home</TextLink>
                            <TextLink to="/room/new">Private room →</TextLink>
                        </>}
                    />

                    <Section
                        title="Account access"
                        subtitle={mode === 'login'
                            ? 'Sign in with your email and password.'
                            : 'Register a new account with your email.'}
                    >
                        <Field label="Email" type="email" value={email}
                            onChange={e => setEmail(e.target.value)} autoComplete="email" />

                        {mode === 'register' && (
                            <Field label="Display name" value={displayName}
                                onChange={e => setDisplayName(e.target.value)}
                                autoComplete="nickname" style={{ marginTop: '0.85rem' }} />
                        )}

                        <Field label="Password" type="password" value={password}
                            onChange={e => setPassword(e.target.value)}
                            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                            style={{ marginTop: '0.85rem' }} />

                        {error && <Note tone="error">{error}</Note>}

                        <ToolsRow>
                            <Button variant="primary" onClick={submit}>
                                {mode === 'login' ? 'Sign in' : 'Create account'}
                            </Button>
                            <Button onClick={() => { setError(''); setMode(mode === 'login' ? 'register' : 'login'); }}>
                                {mode === 'login' ? 'Need an account?' : 'Have an account?'}
                            </Button>
                        </ToolsRow>
                    </Section>
                </Card>
            </Shell>
        </Page>
    );
}
