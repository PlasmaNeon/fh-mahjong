import { NavLink } from 'react-router-dom'
import { useI18n } from '../../i18n/I18nContext'

export default function ToolTabs() {
  const { t } = useI18n()
  return (
    <nav className="tool-tabs" aria-label={t('tools.tabs')}>
      <NavLink to="/tools/calc" className={({ isActive }) => isActive ? 'is-active' : ''}>{t('tools.scoring')}</NavLink>
      <NavLink to="/tools/shanten" className={({ isActive }) => isActive ? 'is-active' : ''}>{t('tools.shanten')}</NavLink>
    </nav>
  )
}
