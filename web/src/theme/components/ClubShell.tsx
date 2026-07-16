import type { ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import type { AuthRouteState } from '../../features/auth/authModal'
import Page from './Page'
import Shell from './Shell'

export default function ClubShell({ children, wide = false, title, navigationLocked = false }: {
  children: ReactNode
  wide?: boolean
  title?: string
  navigationLocked?: boolean
}) {
  const location = useLocation()
  const { status } = useAuth()
  const signedIn = status === 'authenticated'
  const profileState: AuthRouteState | undefined = signedIn ? undefined : { backgroundLocation: location, optionalAuth: true }

  return (
    <Page>
      <header className="club-nav">
        <Link className="club-nav__brand" to="/" aria-label="Rainy Mahjong Club main menu">
          <span aria-hidden="true">東</span>
          <strong>Rainy Mahjong Club</strong>
        </Link>
        <div className="club-nav__context">{title}</div>
        <nav className="club-nav__actions" aria-label="Club navigation">
          {navigationLocked ? <span className="club-nav__locked">Search in progress</span> : <>
          <Link to={signedIn ? '/account' : `/login?returnTo=${encodeURIComponent('/account')}`} state={profileState}>Profile</Link>
          </>}
        </nav>
      </header>
      <Shell wide={wide}>{children}</Shell>
    </Page>
  )
}
