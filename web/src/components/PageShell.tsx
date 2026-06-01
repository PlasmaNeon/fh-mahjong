import type { ReactNode } from 'react'

// PageShell — the shared "Tabletop Glass" page background and centered container.
// Layered radial emerald glow over a deep teal -> navy gradient. Every non-game
// page wraps its content in this so the whole app shares one backdrop.
export default function PageShell({
    children,
    maxWidth = 'max-w-6xl',
    className = '',
}: {
    children: ReactNode
    maxWidth?: string
    className?: string
}) {
    return (
        <div className="min-h-screen bg-[radial-gradient(circle_at_50%_18%,_rgba(16,185,129,0.18),_transparent_22%),linear-gradient(180deg,_#03111a_0%,_#06352d_58%,_#041019_100%)] text-white">
            <div className={`mx-auto flex min-h-screen w-full ${maxWidth} flex-col px-6 py-10 ${className}`}>
                {children}
            </div>
        </div>
    )
}
