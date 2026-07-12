import { useState } from 'react'
import { GameDialog } from '../../theme'

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
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="table-exit-control"
        style={{ top: 'calc(env(safe-area-inset-top, 0px) + 1rem)' }}
      >
        Exit
      </button>

      {open && (
        <GameDialog
          eyebrow="Your seat will stay warm"
          title="Leave the match?"
          tone="danger"
          onCancel={() => setOpen(false)}
          actions={<>
            <button type="button" onClick={() => setOpen(false)} className="ldg-btn ldg-btn--primary">
              Stay at table
            </button>
            <button type="button" onClick={() => { setOpen(false); onConfirmLeave() }} className="ldg-btn ldg-btn--danger">
              Leave match
            </button>
          </>}
        >
            <p>
              A bot will play your seat while you&apos;re away. You can rejoin
              anytime from the private table screen.
            </p>
        </GameDialog>
      )}
    </>
  )
}
