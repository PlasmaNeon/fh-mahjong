import { useState } from 'react'
import { loadPrivateRoomSession } from './privateRoomSession'
import { buildRejoinLink } from './rejoinMatch'

type Props = {
  roomId: string
  onConfirmLeave: () => void
}

// Top-right Exit control for the in-play game table. Opens a confirmation
// modal so an accidental tap does not drop the player out of the match.
// On confirm it calls onConfirmLeave, which the parent uses to set the
// left-match marker, close the socket, and navigate to the waiting room.
export default function ExitMatchButton({ roomId, onConfirmLeave }: Props) {
  const [open, setOpen] = useState(false)
  const [copied, setCopied] = useState(false)

  const copyLink = async () => {
    const token = loadPrivateRoomSession(roomId)?.token
    if (!token || typeof window === 'undefined') return
    const link = buildRejoinLink(window.location.origin, roomId, token)
    try {
      await navigator.clipboard.writeText(link)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      // Clipboard can be blocked (e.g. insecure context). Fall back to a prompt.
      window.prompt('Copy your rejoin link:', link)
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="absolute right-4 top-4 z-40 rounded-xl border border-white/15 bg-black/40 px-4 py-2 text-xs font-black uppercase tracking-[0.18em] text-white/85 backdrop-blur transition hover:bg-black/60"
        style={{ top: 'calc(env(safe-area-inset-top, 0px) + 1rem)' }}
      >
        Exit
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-6">
          <div className="w-full max-w-md rounded-[28px] border border-emerald-300/20 bg-slate-950/95 p-8 shadow-[0_22px_70px_rgba(0,0,0,0.5)]">
            <h1 className="text-2xl font-black uppercase tracking-[0.12em] text-emerald-100">
              Leave the match?
            </h1>
            <p className="mt-3 text-sm text-slate-300">
              A bot will play your seat while you&apos;re away. You can rejoin
              anytime from the room.
            </p>

            <div className="mt-6 flex flex-col gap-3">
              <button
                type="button"
                onClick={() => { setOpen(false); onConfirmLeave() }}
                className="w-full rounded-2xl border border-rose-300/30 bg-rose-600 px-5 py-3 text-sm font-black uppercase tracking-[0.18em] text-white hover:bg-rose-500"
              >
                Leave
              </button>
              <button
                type="button"
                onClick={copyLink}
                className="w-full rounded-2xl border border-cyan-300/30 bg-cyan-950/60 px-5 py-3 text-sm font-black uppercase tracking-[0.18em] text-cyan-100 hover:bg-cyan-900/70"
              >
                {copied ? 'Link copied' : 'Copy rejoin link'}
              </button>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="w-full rounded-2xl border border-white/15 bg-transparent px-5 py-3 text-sm font-black uppercase tracking-[0.18em] text-white/80 hover:bg-white/5"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
