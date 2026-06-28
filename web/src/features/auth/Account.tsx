import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSocket } from '../../contexts/SocketContext';
import { getApiUrl } from '../../config';
import { Page, Shell, Card, PageHeader, Section, ToolsRow, Button, TextLink, Field, Note } from '../../theme';

export default function Account() {
    const [email, setEmail] = useState('');
    const [displayName, setDisplayName] = useState('');
    const [currentPassword, setCurrentPassword] = useState('');
    // The values loaded from the server, used to detect what actually changed.
    const [initialEmail, setInitialEmail] = useState('');
    const [initialDisplayName, setInitialDisplayName] = useState('');
    const [status, setStatus] = useState('');
    const [error, setError] = useState('');
    const [loaded, setLoaded] = useState(false);
    const [editable, setEditable] = useState(true);
    const navigate = useNavigate();
    const { connect } = useSocket();

    useEffect(() => {
        const token = localStorage.getItem('fh_token');
        if (!token) { navigate('/login'); return; }
        (async () => {
            try {
                const res = await fetch(getApiUrl('/api/v1/users/me'), {
                    headers: { 'Authorization': `Bearer ${token}` },
                });
                if (res.status === 404 || res.status === 503) {
                    setEditable(false);
                    setLoaded(true);
                    return;
                }
                if (!res.ok) throw new Error('Failed to load profile');
                const data = await res.json();
                setEmail(data.email || '');
                setDisplayName(data.username || '');
                setInitialEmail(data.email || '');
                setInitialDisplayName(data.username || '');
                setLoaded(true);
            } catch (e: any) {
                setError(e.message || 'Failed to load profile');
                setLoaded(true);
            }
        })();
    }, [navigate]);

    const save = async () => {
        setError(''); setStatus('');
        const token = localStorage.getItem('fh_token');
        if (!token) { navigate('/login'); return; }

        const emailChanged = email.trim() !== '' && email.trim() !== initialEmail;
        const nameChanged = displayName.trim() !== '' && displayName.trim() !== initialDisplayName;
        if (!emailChanged && !nameChanged) {
            setError('No changes to save.');
            return;
        }
        // Changing the login email requires the current password.
        if (emailChanged && !currentPassword) {
            setError('Enter your current password to change your email.');
            return;
        }

        try {
            const body: { email?: string; displayName?: string; currentPassword?: string } = {};
            if (emailChanged) { body.email = email.trim(); body.currentPassword = currentPassword; }
            if (nameChanged) body.displayName = displayName.trim();
            const res = await fetch(getApiUrl('/api/v1/users/me'), {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                body: JSON.stringify(body),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Failed to save');
            // The server only returns a token when the display name changed.
            if (data.token) {
                localStorage.setItem('fh_token', data.token);
                connect(data.token);
            }
            setInitialEmail(data.user?.email ?? email.trim());
            setInitialDisplayName(data.user?.username ?? displayName.trim());
            setCurrentPassword('');
            setStatus('Saved.');
        } catch (e: any) {
            setError(e.message || 'Failed to save');
        }
    };

    return (
        <Page>
            <Shell>
                <Card>
                    <PageHeader
                        title="Account"
                        subtitle="账户设置 · 奉化麻将"
                        nav={<>
                            <TextLink to="/play">← Play</TextLink>
                            <TextLink to="/">Home</TextLink>
                        </>}
                    />
                    <Section title="Profile" subtitle="Change your email or display name.">
                        {!loaded && <Note>Loading…</Note>}
                        {loaded && !editable && (
                            <Note tone="error">
                                Guests can't edit a profile. Register an account from the Sign in page.
                            </Note>
                        )}
                        {loaded && editable && (
                            <>
                                <Field label="Email" type="email" value={email}
                                    onChange={e => setEmail(e.target.value)} autoComplete="email" />
                                <Field label="Display name" value={displayName}
                                    onChange={e => setDisplayName(e.target.value)}
                                    autoComplete="nickname" style={{ marginTop: '0.85rem' }} />
                                <Field label="Current password (required to change email)" type="password"
                                    value={currentPassword} onChange={e => setCurrentPassword(e.target.value)}
                                    autoComplete="current-password" style={{ marginTop: '0.85rem' }} />
                                {error && <Note tone="error">{error}</Note>}
                                {status && <Note tone="ok">{status}</Note>}
                                <ToolsRow>
                                    <Button variant="primary" onClick={save}>Save</Button>
                                </ToolsRow>
                            </>
                        )}
                    </Section>
                </Card>
            </Shell>
        </Page>
    );
}
