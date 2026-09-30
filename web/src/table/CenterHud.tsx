import type { HudChip, TileLike } from './types'
import { TileComponent } from './Tile'
import { useI18n } from '../i18n/I18nContext'

export type CenterHudSeat = {
  direction: 'bottom' | 'right' | 'top' | 'left'
  windKanji: string
  score: number
  isActive: boolean
}

type CenterHudProps = {
  wildTile?: TileLike
  hudChips: HudChip[]
  seats: CenterHudSeat[]
}

export function CenterHud({ wildTile, hudChips, seats }: CenterHudProps) {
  const { t } = useI18n()
  return (
    <div className="center-info text-white text-center">
      <div className="center-info-panel">
        <div className="center-info-content">
          {wildTile && (
            <div className="center-wild" role="group" aria-label={t('game.wildTile')}>
              <span className="center-wild-label">{t('game.wildTile')}</span>
              <div className="center-wild-face">
                <TileComponent tile={wildTile} size="small" noGlow />
              </div>
            </div>
          )}
          <div className="center-info-stats">
            {hudChips.map((chip, index) => (
              <span
                key={`${chip.label}-${index}`}
                className={`center-info-chip${chip.tone === 'danger' ? ' center-info-chip--danger' : ''}`}
              >
                {chip.label}
              </span>
            ))}
          </div>
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
