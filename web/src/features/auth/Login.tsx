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
import { useI18n } from '../../i18n/I18nContext'

export default function Login() {
  const navigate = useNavigate()
  const { connect } = useSocket()
  const { status } = useAuth()
  const { t } = useI18n()
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
      title={invite ? t('auth.invited') : t('auth.enterClub')}
      subtitle={invite ? t('auth.inviteHelp', { table: invite }) : t('auth.remembered')}
      dismissible={dialogMode.dismissible}
      onCancel={dialogMode.dismissible ? close : undefined}
    >
      {status === 'offline' && <Note tone="error">{t('auth.retryOffline')}</Note>}
      <AuthTicket intent={invite ? 'join table' : 'continue'} onAuthenticated={() => { connect(); navigate(returnTo, { replace: true }) }} />
    </AuthDialog>
  )
}
