// Full-viewport themed loading screen: accent spinner ring + label, on the
// ledger theme background. Shared by every "waiting" state so they stay consistent.
export default function LoadingScreen({ label }: { label: string }) {
    return (
        <div className="ledger-page ldg-loading">
            <div className="ldg-loading__inner">
                <div className="ldg-loading__spinner" aria-hidden="true" />
                <div className="ldg-loading__label" role="status">{label}</div>
            </div>
        </div>
    )
}
