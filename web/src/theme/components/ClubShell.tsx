import type { ReactNode } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import Page from './Page'
import Shell from './Shell'

export default function ClubShell({ children, wide = false, title, navigationLocked = false }: {
  children: ReactNode
  wide?: boolean
  title?: string
  navigationLocked?: boolean
}) {
  const navigate = useNavigate()
  const location = useLocation()
  const canGoBack = location.key !== 'default'

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
          {location.pathname !== '/' && (
            <button type="button" className="club-nav__back" onClick={() => canGoBack ? navigate(-1) : navigate('/')}>
              Back
            </button>
          )}
          <Link to="/account">Profile</Link>
          </>}
        </nav>
      </header>
      <Shell wide={wide}>{children}</Shell>
    </Page>
  )
}
