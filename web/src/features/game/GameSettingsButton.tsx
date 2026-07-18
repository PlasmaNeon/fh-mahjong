import { useState } from 'react'
import { GameDialog } from '../../theme'
import type { DiscardMode } from './discardMode'
import { useI18n } from '../../i18n/I18nContext'

type Props = {
  mode: DiscardMode
  onChange: (mode: DiscardMode) => void
}

// Top-left gear control for the in-play table. Opens a settings dialog whose
// only option (for now) is the discard interaction mode.
export default function GameSettingsButton({ mode, onChange }: Props) {
  const [open, setOpen] = useState(false)
  const { t } = useI18n()
  const options = [
    { value: 'single' as const, title: t('settings.single'), desc: t('settings.singleHelp') },
    { value: 'double' as const, title: t('settings.double'), desc: t('settings.doubleHelp') },
  ]
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="table-settings-control"
        aria-label={t('settings.label')}
        style={{ top: 'calc(env(safe-area-inset-top, 0px) + 1rem)' }}
      >
        ⚙
      </button>

      {open && (
        <GameDialog
          eyebrow={t('settings.eyebrow')}
          title={t('settings.label')}
          onCancel={() => setOpen(false)}
          actions={
            <button type="button" onClick={() => setOpen(false)} className="ldg-btn ldg-btn--primary">
              {t('settings.done')}
            </button>
          }
        >
          <div className="settings-field">
            <div className="settings-field__label">{t('settings.discard')}</div>
            <div className="settings-choice">
              {options.map((opt) => (
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
