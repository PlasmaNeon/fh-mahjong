import { useState } from 'react'
import { GameDialog } from '../../theme'
import { useI18n } from '../../i18n/I18nContext'

type Props = {
  roomId: string
  onConfirmLeave: () => void
}

// Top-right Exit control for the in-play game table. Opens a confirmation
// modal so an accidental tap does not drop the player out of the match.
// On confirm it calls onConfirmLeave, which the parent uses to set the
// left-match marker, close the socket, and navigate to the waiting room.
export default function ExitMatchButton({ onConfirmLeave }: Props) {
  const [open, setOpen] = useState(false)
  const { t } = useI18n()
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="table-exit-control"
        style={{ top: 'calc(env(safe-area-inset-top, 0px) + 1rem)' }}
      >
        {t('common.exit')}
      </button>

      {open && (
        <GameDialog
          eyebrow={t('game.exitEyebrow')}
          title={t('game.leaveTitle')}
          tone="danger"
          onCancel={() => setOpen(false)}
          actions={<>
            <button type="button" onClick={() => setOpen(false)} className="ldg-btn ldg-btn--primary">
              {t('game.stay')}
            </button>
            <button type="button" onClick={() => { setOpen(false); onConfirmLeave() }} className="ldg-btn ldg-btn--danger">
              {t('game.leave')}
            </button>
          </>}
        >
            <p>{t('game.leaveHelp')}</p>
        </GameDialog>
      )}
    </>
  )
}
