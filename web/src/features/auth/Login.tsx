import { useCallback } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { useSocket } from '../../contexts/SocketContext'
import { useAuth } from '../../contexts/AuthContext'
import { Note } from '../../theme'
import AuthTicket from './AuthTicket'
import { safeReturnTo } from './authClient'
import AuthDialog from './AuthDialog'
import { resolveAuthDialogMode, type AuthRouteState } from './authModal'
import { clearPlayIntent } from '../lobby/navigation'

export default function Login() {
  const navigate = useNavigate()
  const { connect } = useSocket()
  const { status } = useAuth()
  const [searchParams] = useSearchParams()
  const location = useLocation()
  const routeState = location.state as AuthRouteState | null
  const returnToParam = searchParams.get('returnTo')
  const returnTo = safeReturnTo(returnToParam)
  const invite = returnTo.match(/^\/room\/([^/?#]+)/)?.[1]
  const dialogMode = resolveAuthDialogMode({ hasBackground: Boolean(routeState?.backgroundLocation), optional: Boolean(routeState?.optionalAuth), returnToParam })

  const close = useCallback(() => {
    if (routeState?.cancelIntent === 'quick-match' && typeof window !== 'undefined') clearPlayIntent(window.sessionStorage)
    if (routeState?.backgroundLocation) navigate(-1)
    else if (dialogMode.closeTo) navigate(dialogMode.closeTo, { replace: true })
  }, [dialogMode.closeTo, navigate, routeState])

  return (
    <AuthDialog
      title={invite ? "You’ve been invited" : 'Enter the club'}
      subtitle={invite ? `Private table ${invite}. Sign in or create an account to join.` : 'Sign in once and this device stays remembered for 30 days.'}
      dismissible={dialogMode.dismissible}
      onCancel={dialogMode.dismissible ? close : undefined}
    >
      {status === 'offline' && <Note tone="error">The club is offline. You can retry when your connection returns.</Note>}
      <AuthTicket intent={invite ? 'join table' : 'continue'} onAuthenticated={() => { connect(); navigate(returnTo, { replace: true }) }} />
    </AuthDialog>
  )
}
