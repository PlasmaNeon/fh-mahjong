import type { ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import type { AuthRouteState } from '../../features/auth/authRouteState'
import { useI18n } from '../../i18n/I18nContext'
import DirectShell from './DirectShell'

export default function ClubShell({ children, wide = false, title, navigationLocked = false }: {
  children: ReactNode
  wide?: boolean
  title?: string
  navigationLocked?: boolean
}) {
  const location = useLocation()
  const { status } = useAuth()
  const { t } = useI18n()
  const signedIn = status === 'authenticated'
  const profileState: AuthRouteState | undefined = signedIn ? undefined : { backgroundLocation: location, optionalAuth: true }

  return <DirectShell title={title} navigationLocked={navigationLocked} profile={
    <Link to={signedIn ? '/account' : `/login?returnTo=${encodeURIComponent('/account')}`} state={profileState}>{t('nav.profile')}</Link>
  }>
    <div className={wide ? 'direct-shell-content direct-shell-content--wide' : 'direct-shell-content'}>{children}</div>
  </DirectShell>
}
