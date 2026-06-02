import type { ReactNode } from 'react'

// Horizontal row of buttons/links. `end` right-aligns them.
export default function ToolsRow({ end = false, children }: { end?: boolean; children: ReactNode }) {
    return <div className={`ldg-tools-row${end ? ' ldg-tools-row--end' : ''}`}>{children}</div>
}
