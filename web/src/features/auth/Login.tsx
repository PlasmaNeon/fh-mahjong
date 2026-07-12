import { useNavigate } from 'react-router-dom'
import { useSocket } from '../../contexts/SocketContext'
import { Card, ClubShell, PageHeader, Section } from '../../theme'
import AuthTicket from './AuthTicket'

export default function Login() {
  const navigate = useNavigate()
  const { connect } = useSocket()

  return (
    <ClubShell title="Account">
      <Card>
        <PageHeader title="Enter the club" subtitle="登录 · 奉化麻将" />
        <Section title="Your table is waiting" subtitle="Sign in or make an account, then continue directly to Play.">
          <AuthTicket onAuthenticated={token => { connect(token); navigate('/play', { replace: true }) }} />
        </Section>
      </Card>
    </ClubShell>
  )
}
