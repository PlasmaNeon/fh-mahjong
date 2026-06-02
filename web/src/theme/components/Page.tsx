import type { ReactNode } from 'react'

// Full-viewport themed page background (var(--page) + min-height).
export default function Page({ children }: { children: ReactNode }) {
    return <div className="ledger-page">{children}</div>
}
