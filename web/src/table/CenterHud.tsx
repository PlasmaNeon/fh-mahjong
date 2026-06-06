import type { HudChip } from './TableScene'

export type CenterHudSeat = {
  direction: 'bottom' | 'right' | 'top' | 'left'
  windKanji: string
  score: number
  isActive: boolean
}

type CenterHudProps = {
  hudChips: HudChip[]
  seats: CenterHudSeat[]
}

export function CenterHud({ hudChips, seats }: CenterHudProps) {
  return (
    <div className="center-info text-white text-center">
      <div className="center-info-panel">
        <div className="center-info-stats">
          {hudChips.map((chip, index) => (
            <span
              key={`${chip.label}-${index}`}
              className="center-info-chip"
              style={chip.tone === 'danger' ? { color: '#ff6b6b' } : undefined}
            >
              {chip.label}
            </span>
          ))}
        </div>

        {seats.map((seat) => (
          <div
            key={seat.direction}
            className={`center-seat center-seat-${seat.direction} ${seat.isActive ? 'center-seat-active' : ''}`}
          >
            {seat.windKanji && <span className="center-seat-wind">{seat.windKanji}</span>}
            <span className="center-seat-score">{seat.score}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
