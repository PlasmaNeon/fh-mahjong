import type { CSSProperties, ReactNode } from 'react'

// Small helper/status text. tone drives the accent/danger color.
export default function Note({
    tone = 'default',
    style,
    children,
}: {
    tone?: 'default' | 'ok' | 'error'
    style?: CSSProperties
    children: ReactNode
}) {
    const t = tone === 'ok' ? ' ldg-note--ok' : tone === 'error' ? ' ldg-note--err' : ''
    return (
        <p className={`ldg-note${t}`} style={style}>
            {children}
        </p>
    )
}
