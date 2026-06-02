import type { ReactNode } from 'react'

// Centered content column. `wide` widens it (e.g. seat grids, tools).
export default function Shell({ wide = false, children }: { wide?: boolean; children: ReactNode }) {
    return <div className={`ledger-shell${wide ? ' ledger-shell--wide' : ''}`}>{children}</div>
}
