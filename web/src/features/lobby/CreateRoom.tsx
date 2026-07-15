import { useCallback, useEffect, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { useSocket } from '../../contexts/SocketContext'
import { Button, Card, ClubShell, Note, PageHeader, Section, ToolsRow } from '../../theme'

export default function CreateRoom() {
  const { status, apiFetch, refreshSession } = useAuth()
  const { connect } = useSocket()
  const navigate = useNavigate()
  const [attempt, setAttempt] = useState(0)
  const [error, setError] = useState('')

  const createRoom = useCallback(async () => {
    setError('')
    try {
      const response = await apiFetch('/api/v1/rooms', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data.error || 'Could not create private table')
      connect()
      navigate(`/room/${data.tableId}`, { replace: true })
    } catch (reason) {
      setError(reason instanceof TypeError ? 'The club is offline. No table was created.' : reason instanceof Error ? reason.message : 'Could not create private table')
    }
  }, [apiFetch, connect, navigate])

  useEffect(() => {
    if (status === 'authenticated') void createRoom()
  }, [status, attempt, createRoom])

  if (status === 'anonymous') return <Navigate to={`/login?returnTo=${encodeURIComponent('/room/new')}`} replace />

  return (
    <ClubShell title="Private Table">
      <Card>
        <PageHeader title="Opening your table" subtitle="Private room · host seat East" />
        <Section title={error ? 'The table stayed closed' : 'Setting the felt'} subtitle={error ? 'Nothing was created. Try again when the connection is ready.' : 'We’ll show the invite link after the server confirms your room.'}>
          {status === 'loading' && <Note>Checking your club pass…</Note>}
          {status === 'offline' && <><Note tone="error">The club is offline. No table was created.</Note><ToolsRow><Button variant="primary" onClick={() => void refreshSession()}>Try Again</Button></ToolsRow></>}
          {status === 'authenticated' && !error && <Note>Reserving a private table…</Note>}
          {error && <><Note tone="error">{error}</Note><ToolsRow><Button variant="primary" onClick={() => setAttempt(value => value + 1)}>Try Again</Button></ToolsRow></>}
        </Section>
      </Card>
    </ClubShell>
  )
}
