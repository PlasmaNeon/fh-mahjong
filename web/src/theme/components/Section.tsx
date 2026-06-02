import type { ReactNode } from 'react'

// A hairline-rhythm section with an optional title row (title + subtitle + right-aligned meta).
export default function Section({
    title,
    subtitle,
    meta,
    children,
}: {
    title?: ReactNode
    subtitle?: ReactNode
    meta?: ReactNode
    children: ReactNode
}) {
    const hasRow = title != null || meta != null
    return (
        <section className="ldg-section">
            {hasRow && (
                <div className="ldg-section-row">
                    {title != null ? (
                        <h2 className="ldg-section-title">
                            {title}
                            {subtitle && <small>{subtitle}</small>}
                        </h2>
                    ) : (
                        <span />
                    )}
                    {meta != null && <span className="ldg-section-meta">{meta}</span>}
                </div>
            )}
            {children}
        </section>
    )
}
