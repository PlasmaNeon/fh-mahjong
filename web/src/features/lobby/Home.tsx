import { Link, useLocation, type LinkProps } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import type { AuthRouteState } from '../auth/authRouteState'
import { useI18n } from '../../i18n/I18nContext'

export default function Home() {
    const { status, user } = useAuth()
    const { t, toggleLanguage } = useI18n()
    const location = useLocation()
    const profileState: AuthRouteState | undefined = user ? undefined : { backgroundLocation: location, optionalAuth: true }
    return (
        <main className="ledger-page">
            <div className="club-home">
                <div className="club-home__brand">
                    <span>奉化麻将 · {t('brand.name')}</span>
                    <button type="button" className="club-home__language" onClick={toggleLanguage}>{t('language.switch')}</button>
                </div>
                <nav className="club-home__menu" aria-label={t('nav.menu')}>
                    <div className="club-home__compass" aria-hidden="true"><span>東</span></div>
                    <div className="club-home__links">
                        <HomeLink to="/play" title={t('nav.play')} mark={t('home.enter')} primary />
                        <HomeLink to="/tools/calc" title={t('nav.tools')} mark={t('home.tools')} />
                        <HomeLink to="/replay" title={t('nav.replay')} mark={t('home.paipu')} />
                        <HomeLink to={user ? '/account' : `/login?returnTo=${encodeURIComponent('/account')}`} state={profileState} title={t('nav.profile')} mark={status === 'loading' ? '…' : t('home.you')} />
                    </div>
                </nav>
            </div>
        </main>
    )
}

function HomeLink({ to, state, title, mark, primary = false }: { to: string; state?: LinkProps['state']; title: string; mark: string; primary?: boolean }) {
    return <Link className={`club-home__link${primary ? ' club-home__link--primary' : ''}`} to={to} state={state}><strong>{title}</strong><span className="club-home__link-mark">{mark} →</span></Link>
}
