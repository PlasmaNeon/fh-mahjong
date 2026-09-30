import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useI18n } from '../../i18n/I18nContext'
import '../direct-tools.css'

/** Light workbench shell; calculator state stays owned by each tool. */
export default function ToolsShell({ children, title }: { children: ReactNode; title: string }) {
  const { t, toggleLanguage } = useI18n()
  const playUrl = import.meta.env.DEV ? '/ui-prototype.html#play' : '/play'
  const replayUrl = import.meta.env.DEV ? '/ui-prototype.html#replays' : '/replay'
  const navigation = <nav className="direct-tools-nav" aria-label={t('nav.menu')}>
    <a href={playUrl}>{t('nav.play')}</a>
    <a href={replayUrl}>{t('nav.replay')}</a>
    <Link to="/tools/calc" aria-current="page">{t('nav.tools')}</Link>
  </nav>
  return <div className="direct-tools" data-theme="direct-tools">
    <header className="direct-tools-header">
      <a className="direct-tools-brand" href={playUrl}>奉化麻将<small>Fenghua Mahjong</small></a>
      {navigation}
      <button className="direct-tools-language" onClick={toggleLanguage}>{t('language.switch')}</button>
    </header>
    <main className="direct-tools-main">
      <h1 className="direct-tools-sr-only">{title}</h1>
      {children}
    </main>
    <div className="direct-tools-mobile-nav">{navigation}</div>
  </div>
}
