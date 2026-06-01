import type { ReactNode } from 'react'

// GlassCard — the shared dark glass surface used for every panel/section on
// non-game pages. Pass `className` to tint the border or change padding.
export default function GlassCard({
    children,
    className = '',
}: {
    children: ReactNode
    className?: string
}) {
    return (
        <div
            className={`rounded-[28px] border border-white/10 bg-slate-950/62 p-8 shadow-[0_22px_70px_rgba(0,0,0,0.3)] backdrop-blur-sm ${className}`}
        >
            {children}
        </div>
    )
}
