import type { ReactNode } from 'react'

// PageHeading — the large uppercase display heading for non-game pages.
export default function PageHeading({
    children,
    className = '',
}: {
    children: ReactNode
    className?: string
}) {
    return (
        <h1 className={`text-4xl font-black uppercase tracking-[0.12em] text-emerald-100 sm:text-5xl ${className}`}>
            {children}
        </h1>
    )
}
