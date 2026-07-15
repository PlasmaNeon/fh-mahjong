import { Button } from './Button'

// Full-viewport Rainy Club loading screen: wind-compass mark + status label.
// Shared by every waiting state so they stay consistent.
export default function LoadingScreen({ label, onRetry }: { label: string; onRetry?: () => void }) {
    return (
        <div className="ledger-page ldg-loading">
            <div className="ldg-loading__inner">
                <div className="ldg-loading__spinner" aria-hidden="true" />
                <div className="ldg-loading__label" role="status">{label}</div>
                {onRetry && <Button variant="primary" onClick={onRetry}>Try Again</Button>}
            </div>
        </div>
    )
}
