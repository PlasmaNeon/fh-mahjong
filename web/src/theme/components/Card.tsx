import type { ReactNode } from 'react'

// The single bordered surface card that holds a page's content.
export default function Card({ children }: { children: ReactNode }) {
    return <article className="ldg-page">{children}</article>
}
