import type { ReactNode } from 'react'

// Eyebrow — the small black-weight uppercase label that sits above headings.
export default function Eyebrow({
    children,
    className = '',
}: {
    children: ReactNode
    className?: string
}) {
    return (
        <p className={`text-[11px] font-black uppercase tracking-[0.34em] text-emerald-300/78 ${className}`}>
            {children}
        </p>
    )
}
