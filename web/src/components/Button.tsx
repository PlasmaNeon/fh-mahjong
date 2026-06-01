import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Link } from 'react-router-dom'

// Shared button styling for the Tabletop Glass theme.
//   primary   — emerald fill + glow (the main call-to-action)
//   secondary — cyan glass (alternate action, e.g. private room)
//   ghost     — translucent slate (tertiary / back links)
export type ButtonVariant = 'primary' | 'secondary' | 'ghost'

const base =
    'inline-block text-center rounded-[24px] px-7 py-3 text-sm font-black uppercase tracking-[0.18em] transition hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-45'

const variants: Record<ButtonVariant, string> = {
    primary:
        'border border-emerald-300/24 bg-emerald-600 text-white shadow-[0_20px_40px_rgba(5,150,105,0.32)] hover:bg-emerald-500',
    secondary: 'border border-cyan-300/20 bg-cyan-950/60 text-cyan-100 hover:bg-cyan-900/70',
    ghost: 'border border-white/10 bg-white/5 text-slate-100 hover:bg-white/10',
}

// ButtonLink — a react-router <Link> styled as a button.
export function ButtonLink({
    to,
    variant = 'primary',
    className = '',
    children,
}: {
    to: string
    variant?: ButtonVariant
    className?: string
    children: ReactNode
}) {
    return (
        <Link to={to} className={`${base} ${variants[variant]} ${className}`}>
            {children}
        </Link>
    )
}

// Button — a native <button> styled the same way.
export function Button({
    variant = 'primary',
    className = '',
    children,
    ...rest
}: {
    variant?: ButtonVariant
    className?: string
    children: ReactNode
} & ButtonHTMLAttributes<HTMLButtonElement>) {
    return (
        <button className={`${base} ${variants[variant]} ${className}`} {...rest}>
            {children}
        </button>
    )
}
