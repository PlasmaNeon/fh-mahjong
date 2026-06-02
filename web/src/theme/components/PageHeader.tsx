import type { ReactNode } from 'react'

// Page title (with optional secondary subtitle) + optional right-side nav slot.
export default function PageHeader({
    title,
    subtitle,
    nav,
}: {
    title: ReactNode
    subtitle?: ReactNode
    nav?: ReactNode
}) {
    return (
        <div className="ldg-page-head">
            <div>
                <h1 className="ldg-page-head__title">
                    {title}
                    {subtitle && <small>{subtitle}</small>}
                </h1>
            </div>
            {nav && <div className="ldg-page-head__nav">{nav}</div>}
        </div>
    )
}
