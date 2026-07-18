import type { ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import type { AuthRouteState } from '../../features/auth/authModal'
import { useI18n } from '../../i18n/I18nContext'
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
  const { t, toggleLanguage } = useI18n()
  const signedIn = status === 'authenticated'
  const profileState: AuthRouteState | undefined = signedIn ? undefined : { backgroundLocation: location, optionalAuth: true }

  return (
    <Page>
      <header className="club-nav">
        <Link className="club-nav__brand" to="/" aria-label={t('nav.mainMenu')}>
          <span aria-hidden="true">東</span>
          <strong>{t('brand.name')}</strong>
        </Link>
        <div className="club-nav__context">{title}</div>
        <nav className="club-nav__actions" aria-label={t('nav.club')}>
          <button type="button" className="ldg-link" onClick={toggleLanguage}>{t('language.switch')}</button>
          {navigationLocked ? <span className="club-nav__locked">{t('nav.searching')}</span> : <>
          <Link to={signedIn ? '/account' : `/login?returnTo=${encodeURIComponent('/account')}`} state={profileState}>{t('nav.profile')}</Link>
          </>}
        </nav>
      </header>
      <Shell wide={wide}>{children}</Shell>
    </Page>
  )
}
