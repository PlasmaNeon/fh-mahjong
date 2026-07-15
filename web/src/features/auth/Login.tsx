import { useNavigate, useSearchParams } from 'react-router-dom'
import { useSocket } from '../../contexts/SocketContext'
import { useAuth } from '../../contexts/AuthContext'
import { Card, ClubShell, Note, PageHeader, Section } from '../../theme'
import AuthTicket from './AuthTicket'
import { safeReturnTo } from './authClient'

export default function Login() {
  const navigate = useNavigate()
  const { connect } = useSocket()
  const { status } = useAuth()
  const [searchParams] = useSearchParams()
  const returnTo = safeReturnTo(searchParams.get('returnTo'))
  const invite = returnTo.match(/^\/room\/([^/?#]+)/)?.[1]

  return (
    <ClubShell title="Account">
      <Card>
        <PageHeader title={invite ? "You’ve been invited" : 'Enter the club'} subtitle={invite ? `Private table · ${invite}` : '登录 · 奉化麻将'} />
        <Section title={invite ? 'Your seat needs an account' : 'Your table is waiting'} subtitle={invite ? 'Sign in or create an account. We’ll take you straight to the table.' : 'Sign in once and the club will remember this device for 30 days.'}>
          {status === 'offline' && <Note tone="error">The club is offline. You can retry below when your connection returns.</Note>}
          <AuthTicket intent={invite ? 'join table' : 'continue'} onAuthenticated={() => { connect(); navigate(returnTo, { replace: true }) }} />
        </Section>
      </Card>
    </ClubShell>
  )
}
