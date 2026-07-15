import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { useSocket } from '../../contexts/SocketContext'
import { ClubShell, Card, PageHeader, Section, ToolsRow, Button, Field, Note } from '../../theme'
import type { AuthPayload } from './authClient'

export default function Account() {
    const { status: authStatus, user, apiFetch, completeAuth, logout, refreshSession } = useAuth()
    const { connect, disconnect } = useSocket()
    const [email, setEmail] = useState('')
    const [username, setUsername] = useState('')
    const [currentPassword, setCurrentPassword] = useState('')
    const [initialEmail, setInitialEmail] = useState('')
    const [initialUsername, setInitialUsername] = useState('')
    const [status, setStatus] = useState('')
    const [error, setError] = useState('')
    const navigate = useNavigate()

    useEffect(() => {
        if (authStatus === 'anonymous') {
            navigate(`/login?returnTo=${encodeURIComponent('/account')}`, { replace: true })
            return
        }
        if (user) {
            setEmail(user.email)
            setUsername(user.username)
            setInitialEmail(user.email)
            setInitialUsername(user.username)
        }
    }, [authStatus, navigate, user])

    const save = async () => {
        setError(''); setStatus('')
        const emailChanged = email.trim() !== initialEmail
        const usernameChanged = username.trim() !== initialUsername
        if (!emailChanged && !usernameChanged) { setError('No changes to save.'); return }
        if (emailChanged && !currentPassword) { setError('Enter your current password to change your email.'); return }
        try {
            const body: { email?: string; username?: string; currentPassword?: string } = {}
            if (emailChanged) { body.email = email.trim(); body.currentPassword = currentPassword }
            if (usernameChanged) body.username = username.trim()
            const response = await apiFetch('/api/v1/users/me', { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
            const data = await response.json().catch(() => ({}))
            if (!response.ok) throw new Error(data.error || 'Failed to save account')
            completeAuth(data as AuthPayload)
            setInitialEmail(data.user.email)
            setInitialUsername(data.user.username)
            setEmail(data.user.email)
            setUsername(data.user.username)
            setCurrentPassword('')
            if (usernameChanged) { disconnect(); connect() }
            setStatus('Account saved.')
        } catch (reason) {
            setError(reason instanceof Error ? reason.message : 'Failed to save account')
        }
    }

    const signOut = async () => {
        try {
            await logout()
            disconnect()
            navigate('/', { replace: true })
        } catch (reason) {
            setError(reason instanceof Error ? reason.message : 'Could not sign out.')
        }
    }

    return (
        <ClubShell title="Profile">
            <Card>
                <PageHeader title="Account" subtitle="账户设置 · remembered for 30 days" />
                <Section title="Club identity" subtitle="Your unique username appears at every table and can also be used to sign in.">
                    {authStatus === 'loading' && <Note>Checking your club pass…</Note>}
                    {authStatus === 'offline' && <><Note tone="error">The club is offline. Your session has not been changed.</Note><ToolsRow><Button variant="primary" onClick={() => void refreshSession()}>Try Again</Button></ToolsRow></>}
                    {user && <>
                        <Field label="Username" value={username} onChange={event => setUsername(event.target.value)} autoComplete="username" />
                        <Field label="Email" type="email" value={email} onChange={event => setEmail(event.target.value)} autoComplete="email" style={{ marginTop: '0.85rem' }} />
                        <Field label="Current password (required to change email)" type="password" value={currentPassword} onChange={event => setCurrentPassword(event.target.value)} autoComplete="current-password" style={{ marginTop: '0.85rem' }} />
                        {error && <Note tone="error">{error}</Note>}
                        {status && <Note tone="ok">{status}</Note>}
                        <ToolsRow><Button variant="primary" onClick={save}>Save Account</Button><Button onClick={signOut}>Sign Out</Button></ToolsRow>
                    </>}
                </Section>
            </Card>
        </ClubShell>
    )
}
