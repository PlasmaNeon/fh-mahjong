import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { useSocket } from '../../contexts/SocketContext'
import { ClubShell, Card, PageHeader, Section, ToolsRow, Button, Field, Note } from '../../theme'
import type { AuthPayload } from './authClient'
import { useI18n } from '../../i18n/I18nContext'

export default function Account() {
    const { status: authStatus, user, apiFetch, completeAuth, logout, refreshSession } = useAuth()
    const { connect, disconnect } = useSocket()
    const { t } = useI18n()
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
            setEmail(user.email ?? '')
            setUsername(user.username)
            setInitialEmail(user.email ?? '')
            setInitialUsername(user.username)
        }
    }, [authStatus, navigate, user])

    const save = async () => {
        setError(''); setStatus('')
        const emailChanged = email.trim() !== initialEmail
        const usernameChanged = username.trim() !== initialUsername
        if (!emailChanged && !usernameChanged) { setError(t('account.noChanges')); return }
        if (emailChanged && !currentPassword) { setError(t('account.passwordRequired')); return }
        try {
            const body: { email?: string; username?: string; currentPassword?: string } = {}
            if (emailChanged) { body.email = email.trim(); body.currentPassword = currentPassword }
            if (usernameChanged) body.username = username.trim()
            const response = await apiFetch('/api/v1/users/me', { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
            const data = await response.json().catch(() => ({}))
            if (!response.ok) throw new Error(data.error || t('account.saveFailed'))
            completeAuth(data as AuthPayload)
            setInitialEmail(data.user.email ?? '')
            setInitialUsername(data.user.username)
            setEmail(data.user.email ?? '')
            setUsername(data.user.username)
            setCurrentPassword('')
            if (usernameChanged) { disconnect(); connect() }
            setStatus(t('account.saved'))
        } catch (reason) {
            setError(reason instanceof Error ? reason.message : t('account.saveFailed'))
        }
    }

    const signOut = async () => {
        try {
            await logout()
            disconnect()
            navigate('/', { replace: true })
        } catch (reason) {
            setError(reason instanceof Error ? reason.message : t('account.signOutFailed'))
        }
    }

    return (
        <ClubShell title={t('nav.profile')}>
            <Card>
                <PageHeader title={t('account.title')} subtitle={t('account.subtitle')} />
                <Section title={t('account.identity')} subtitle={t('account.identityHelp')}>
                    {authStatus === 'loading' && <Note>{t('account.checking')}</Note>}
                    {authStatus === 'offline' && <><Note tone="error">{t('account.offline')}</Note><ToolsRow><Button variant="primary" onClick={() => void refreshSession()}>{t('common.tryAgain')}</Button></ToolsRow></>}
                    {user && <>
                        <Field label={t('auth.username')} value={username} onChange={event => setUsername(event.target.value)} autoComplete="username" />
                        <Field label={t('auth.emailOptional')} type="email" value={email} onChange={event => setEmail(event.target.value)} autoComplete="email" style={{ marginTop: '0.85rem' }} />
                        <Note>{t('account.emailHelp')}</Note>
                        <Field label={t('auth.currentPassword')} type="password" value={currentPassword} onChange={event => setCurrentPassword(event.target.value)} autoComplete="current-password" style={{ marginTop: '0.85rem' }} />
                        {error && <Note tone="error">{error}</Note>}
                        {status && <Note tone="ok">{status}</Note>}
                        <ToolsRow><Button variant="primary" onClick={save}>{t('account.save')}</Button><Button onClick={signOut}>{t('account.signOut')}</Button></ToolsRow>
                    </>}
                </Section>
            </Card>
        </ClubShell>
    )
}
