import { useCallback, useEffect, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { useSocket } from '../../contexts/SocketContext'
import { Button, Card, ClubShell, Note, PageHeader, Section, ToolsRow } from '../../theme'
import { useI18n } from '../../i18n/I18nContext'

export default function CreateRoom() {
  const { status, apiFetch, refreshSession } = useAuth()
  const { connect } = useSocket()
  const { t } = useI18n()
  const navigate = useNavigate()
  const [attempt, setAttempt] = useState(0)
  const [error, setError] = useState('')

  const createRoom = useCallback(async () => {
    setError('')
    try {
      const response = await apiFetch('/api/v1/rooms', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data.error || t('room.createFailed'))
      connect()
      navigate(`/room/${data.tableId}`, { replace: true })
    } catch (reason) {
      setError(reason instanceof TypeError ? t('room.offlineCreate') : reason instanceof Error ? reason.message : t('room.createFailed'))
    }
  }, [apiFetch, connect, navigate])

  useEffect(() => {
    if (status === 'authenticated') void createRoom()
  }, [status, attempt, createRoom])

  if (status === 'anonymous') return <Navigate to={`/login?returnTo=${encodeURIComponent('/room/new')}`} replace />

  return (
    <ClubShell title={t('lobby.private')}>
      <Card>
        <PageHeader title={t('room.opening')} subtitle={t('room.hostEast')} />
        <Section title={t(error ? 'room.closed' : 'room.setting')} subtitle={t(error ? 'room.closedHelp' : 'room.settingHelp')}>
          {status === 'loading' && <Note>{t('account.checking')}</Note>}
          {status === 'offline' && <><Note tone="error">{t('room.offlineCreate')}</Note><ToolsRow><Button variant="primary" onClick={() => void refreshSession()}>{t('common.tryAgain')}</Button></ToolsRow></>}
          {status === 'authenticated' && !error && <Note>{t('room.reserving')}</Note>}
          {error && <><Note tone="error">{error}</Note><ToolsRow><Button variant="primary" onClick={() => setAttempt(value => value + 1)}>{t('common.tryAgain')}</Button></ToolsRow></>}
        </Section>
      </Card>
    </ClubShell>
  )
}
