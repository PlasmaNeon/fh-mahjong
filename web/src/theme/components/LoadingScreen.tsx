import { Button } from './Button'
import { useI18n } from '../../i18n/I18nContext'
import StatusScreen from './StatusScreen'

export default function LoadingScreen({ label, onRetry }: { label: string; onRetry?: () => void }) {
    const { t } = useI18n()
    return <StatusScreen title={label} loading={!onRetry}
        actions={onRetry && <Button variant="primary" onClick={onRetry}>{t('common.tryAgain')}</Button>} />
}
