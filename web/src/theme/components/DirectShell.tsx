import type { ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useI18n } from '../../i18n/I18nContext'
import '../direct-tools.css'
import '../direct-shell.css'

/** Production navigation shared by entry, rooms, account, replays and tools. */
export default function DirectShell({ children, title, profile, navigationLocked = false }: {
  children: ReactNode
  title?: string
  profile?: ReactNode
  navigationLocked?: boolean
}) {
  const { pathname } = useLocation()
  const { t, toggleLanguage } = useI18n()
  const active = pathname.startsWith('/tools') ? 'tools' : pathname.startsWith('/replay') ? 'replay' : pathname === '/' || pathname === '/play' || pathname.startsWith('/room') ? 'play' : undefined
  const navigation = <nav className="direct-tools-nav" aria-label={t('nav.menu')}>
    {([['play', '/', 'nav.play'], ['replay', '/replay', 'nav.replay'], ['tools', '/tools/calc', 'nav.tools']] as const).map(([key, path, label]) =>
      navigationLocked ? <span key={key} aria-disabled="true">{t(label)}</span> : <Link key={key} to={path} aria-current={active === key ? 'page' : undefined}>{t(label)}</Link>,
    )}
  </nav>
  return <div className="direct-tools direct-shell" data-theme="direct-tools">
    <header className="direct-tools-header">
      {navigationLocked ? <span className="direct-tools-brand">{t('brand.direct')}</span> : <Link className="direct-tools-brand" to="/">{t('brand.direct')}</Link>}
      {navigation}
      <div className="direct-shell-utilities">
        <button type="button" className="direct-tools-language" onClick={toggleLanguage}>{t('language.switch')}</button>
        {navigationLocked ? <span role="status">{t('nav.searching')}</span> : profile}
      </div>
    </header>
    <main className="direct-tools-main" aria-label={title}>
      {children}
    </main>
    <div className="direct-tools-mobile-nav">{navigation}</div>
  </div>
}
