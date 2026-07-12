import { useEffect, useId, useRef } from 'react'
import type { KeyboardEvent as ReactKeyboardEvent, ReactNode } from 'react'

export type GameDialogTone = 'neutral' | 'win' | 'danger'

type DialogKeyEvent = Pick<ReactKeyboardEvent, 'key' | 'preventDefault'>

export function handleDialogKeyDown(event: DialogKeyEvent, onCancel?: () => void) {
  if (event.key !== 'Escape' || !onCancel) return
  event.preventDefault()
  onCancel()
}

export default function GameDialog({
  eyebrow,
  title,
  tone = 'neutral',
  children,
  actions,
  onCancel,
}: {
  eyebrow?: ReactNode
  title: ReactNode
  tone?: GameDialogTone
  children: ReactNode
  actions?: ReactNode
  onCancel?: () => void
}) {
  const titleId = useId()
  const dialogRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    dialogRef.current?.focus()
  }, [])

  return (
    <div className="rain-dialog-backdrop">
      <div
        ref={dialogRef}
        className={`rain-dialog rain-dialog--${tone}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onKeyDown={(event) => handleDialogKeyDown(event, onCancel)}
      >
        <div className="rain-dialog__compass" aria-hidden="true"><span>東</span></div>
        {eyebrow && <div className="rain-dialog__eyebrow">{eyebrow}</div>}
        <h1 id={titleId} className="rain-dialog__title">{title}</h1>
        <div className="rain-dialog__body">{children}</div>
        {actions && <div className="rain-dialog__actions">{actions}</div>}
      </div>
    </div>
  )
}
