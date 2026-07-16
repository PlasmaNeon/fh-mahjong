import { useState } from 'react'
import { GameDialog } from '../../theme'
import type { DiscardMode } from './discardMode'

type Props = {
  mode: DiscardMode
  onChange: (mode: DiscardMode) => void
}

const OPTIONS: { value: DiscardMode; title: string; desc: string }[] = [
  { value: 'single', title: 'Single-click', desc: 'Instant discard on tap' },
  { value: 'double', title: 'Double-click', desc: 'Tap to lift, tap again to confirm' },
]

// Top-left gear control for the in-play table. Opens a settings dialog whose
// only option (for now) is the discard interaction mode.
export default function GameSettingsButton({ mode, onChange }: Props) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="table-settings-control"
        aria-label="Settings"
        style={{ top: 'calc(env(safe-area-inset-top, 0px) + 1rem)' }}
      >
        ⚙
      </button>

      {open && (
        <GameDialog
          eyebrow="Table preferences"
          title="Settings"
          onCancel={() => setOpen(false)}
          actions={
            <button type="button" onClick={() => setOpen(false)} className="ldg-btn ldg-btn--primary">
              Done
            </button>
          }
        >
          <div className="settings-field">
            <div className="settings-field__label">Discard</div>
            <div className="settings-choice">
              {OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  className={`settings-choice__option ${mode === opt.value ? 'is-active' : ''}`}
                  onClick={() => onChange(opt.value)}
                >
                  <span className="settings-choice__title">{opt.title}</span>
                  <span className="settings-choice__desc">{opt.desc}</span>
                </button>
              ))}
            </div>
          </div>
        </GameDialog>
      )}
    </>
  )
}
