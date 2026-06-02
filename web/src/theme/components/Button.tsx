import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Link } from 'react-router-dom'

export type ButtonVariant = 'default' | 'primary' | 'danger'

function btnClass(variant: ButtonVariant, extra = ''): string {
    const v = variant === 'primary' ? ' ldg-btn--primary' : variant === 'danger' ? ' ldg-btn--danger' : ''
    return `ldg-btn${v}${extra ? ` ${extra}` : ''}`
}

// Native button styled by the theme.
export function Button({
    variant = 'default',
    className = '',
    children,
    ...rest
}: { variant?: ButtonVariant; className?: string; children: ReactNode } & ButtonHTMLAttributes<HTMLButtonElement>) {
    return (
        <button className={btnClass(variant, className)} {...rest}>
            {children}
        </button>
    )
}

// react-router <Link> styled identically to Button.
export function ButtonLink({
    to,
    variant = 'default',
    className = '',
    children,
}: {
    to: string
    variant?: ButtonVariant
    className?: string
    children: ReactNode
}) {
    return (
        <Link to={to} className={btnClass(variant, className)}>
            {children}
        </Link>
    )
}
