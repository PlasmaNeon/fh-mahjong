import { useEffect, useId, useRef, type KeyboardEvent, type ReactNode } from 'react'

const focusableSelector = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

export default function AuthDialog({
  title,
  subtitle,
  dismissible,
  onCancel,
  children,
}: {
  title: string
  subtitle: string
  dismissible: boolean
  onCancel?: () => void
  children: ReactNode
}) {
  const titleId = useId()
  const descriptionId = useId()
  const dialogRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const ticket = dialogRef.current?.querySelector<HTMLElement>('.auth-dialog__ticket')
    const firstControl = ticket?.querySelector<HTMLElement>('input:not([disabled])') ?? ticket?.querySelector<HTMLElement>(focusableSelector)
    ;(firstControl ?? dialogRef.current)?.focus()
    return () => {
      document.body.style.overflow = previousOverflow
      previouslyFocused?.focus()
    }
  }, [])

  useEffect(() => {
    if (!dismissible || !onCancel) return
    const handleEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key !== 'Escape') return
      event.preventDefault()
      onCancel()
    }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [dismissible, onCancel])

  const trapFocus = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'Tab') return
    const controls = Array.from(dialogRef.current?.querySelectorAll<HTMLElement>(focusableSelector) ?? [])
    if (controls.length === 0) {
      event.preventDefault()
      dialogRef.current?.focus()
      return
    }
    const first = controls[0]
    const last = controls[controls.length - 1]
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  return (
    <div
      className="auth-dialog-backdrop"
      onMouseDown={(event) => {
        if (dismissible && onCancel && event.target === event.currentTarget) onCancel()
      }}
    >
      <div
        ref={dialogRef}
        className="auth-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        tabIndex={-1}
        onKeyDown={trapFocus}
      >
        <div className="auth-dialog__compass" aria-hidden="true"><span>東</span></div>
        {dismissible && onCancel && (
          <button type="button" className="auth-dialog__close" aria-label="Close sign in" onClick={onCancel}>×</button>
        )}
        <header className="auth-dialog__header">
          <h1 id={titleId}>{title}</h1>
          <p id={descriptionId}>{subtitle}</p>
        </header>
        <div className="auth-dialog__ticket">{children}</div>
      </div>
    </div>
  )
}
