import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

// Hairline-underline text link. Pass `to` for client routes or `href` for raw anchors.
export default function TextLink({
    to,
    href,
    children,
}: {
    to?: string
    href?: string
    children: ReactNode
}) {
    if (to) {
        return (
            <Link to={to} className="ldg-link">
                {children}
            </Link>
        )
    }
    return (
        <a href={href} className="ldg-link">
            {children}
        </a>
    )
}
