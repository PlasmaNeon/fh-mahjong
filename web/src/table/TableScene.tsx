import { useMemo, useRef } from 'react'
import type { ReactNode } from 'react'
import { CenterHud, type CenterHudSeat } from './CenterHud'
import { TileComponent } from './Tile'
import { useTileFlight } from './tileFlight'
import { sortTiles } from './handOrdering'
import { PlayerSeat } from './seat/PlayerSeat'
import { OpenMelds } from './seat/OpenMelds'
import type {
  SeatLaneDirection,
  TileLike,
  MeldLike,
  PlayerTableView,
  HudChip,
  RoundResultBreakdownEntry,
  RoundResultPayout,
  RoundResultView,
} from './types'

export { TileComponent }
export type {
  SeatLaneDirection,
  TileLike,
  MeldLike,
  PlayerTableView,
  HudChip,
  RoundResultBreakdownEntry,
  RoundResultPayout,
  RoundResultView,
}

type TableBoardProps = {
  viewSeat: number
  players: PlayerTableView[]
  activeSeat: number
  wildTiles?: TileLike[]
  hudChips?: HudChip[]
  actionBar?: ReactNode
  cornerInfo?: ReactNode
  canDiscardSeat?: number | null
  onDiscard?: (tile: TileLike) => void
  isWildTile?: (tile: TileLike) => boolean
  animateDiscardTileIds?: Set<number>
  callableDiscard?: { seat: number; tileId: number } | null
}

const WIND_KANJI = ['', '東', '南', '西', '北']
const POSITIONS: SeatLaneDirection[] = ['bottom', 'right', 'top', 'left']

export function getSeatDirection(seat: number, viewSeat: number): SeatLaneDirection {
  return POSITIONS[(seat - viewSeat + 4) % 4]
}

export function TableBoard({
  viewSeat,
  players,
  activeSeat,
  wildTiles = [],
  hudChips = [],
  actionBar = null,
  cornerInfo = null,
  canDiscardSeat = null,
  onDiscard,
  isWildTile = () => false,
  animateDiscardTileIds,
  callableDiscard = null,
}: TableBoardProps) {
  const tableRef = useRef<HTMLDivElement | null>(null)
  const seatViews = useMemo(() => players.map((player) => ({
    player,
    direction: getSeatDirection(player.seat, viewSeat),
  })), [players, viewSeat])

  const { hiddenTileIds, flights } = useTileFlight({ seatViews, isWildTile, tableRef })

  return (
    <div className="mahjong-table" ref={tableRef}>
      {wildTiles.length > 0 && (
        <div className="wild-tile-corner">
          <div className="wild-tile-corner-main">
            <div className="wild-tile-corner-label">Wild Tile</div>
            <div className="wild-tile-corner-face">
              <TileComponent tile={wildTiles[0]} size="small" noGlow />
            </div>
          </div>
          {cornerInfo && <div className="wild-tile-corner-info">{cornerInfo}</div>}
        </div>
      )}

      <CenterHud
        hudChips={hudChips}
        seats={POSITIONS.map((direction) => {
          const seat = players.find((player) => getSeatDirection(player.seat, viewSeat) === direction)
          if (!seat) return null
          return {
            direction,
            windKanji: WIND_KANJI[seat.seatWind ?? 0] || '',
            score: seat.score ?? 0,
            isActive: seat.seat === activeSeat,
          }
        }).filter((seat): seat is CenterHudSeat => seat !== null)}
      />

      {actionBar}

      {seatViews.map(({ player, direction }) => (
        <PlayerSeat
          key={`seat-${player.seat}`}
          direction={direction}
          player={player}
          canDiscard={direction === 'bottom' && player.seat === canDiscardSeat}
          onDiscard={onDiscard}
          isWildTile={isWildTile}
          hiddenTileIds={hiddenTileIds}
          animateDiscardTileIds={animateDiscardTileIds}
          callableDiscard={callableDiscard}
        />
      ))}

      {flights}
    </div>
  )
}

export function TableRoundResultOverlay({
  result,
  isWildTile = () => false,
}: {
  result?: RoundResultView | null
  isWildTile?: (tile: TileLike) => boolean
}) {
  if (!result) return null

  const breakdown = result.breakdown || []
  const payouts = result.payouts || []
  const closedHand = sortTiles(result.closedHand || [])
  const winningMelds = result.winningMelds || []
  const flowers = result.flowers || []

  return (
    <div className="round-result-overlay">
      <div className="round-result-modal">
        {result.isDraw ? (
          <div className="round-result-draw">
            <div className="round-result-badge round-result-badge-draw">Draw</div>
            <h2 className="round-result-title round-result-title-draw">Exhaustive Draw</h2>
            <p className="round-result-subtitle">No tiles remaining in the wall.</p>
          </div>
        ) : (
          <>
            <div className="round-result-header-line">
              <div className={`round-result-badge ${result.winType === 'tsumo' ? 'round-result-badge-tsumo' : 'round-result-badge-ron'}`}>
                {result.winType === 'tsumo' ? 'TSUMO!' : 'RON!'}
              </div>
              <h2 className={`round-result-title ${result.winType === 'tsumo' ? 'round-result-title-tsumo' : 'round-result-title-ron'}`}>
                {result.winnerLabel}
              </h2>
            </div>

            {result.discarderLabel && (
              <p className="round-result-subtitle">{result.discarderLabel}</p>
            )}

            <div className="round-result-panel round-result-panel-plain round-result-hand-panel">
              <div className="round-result-hand-row">
                <div className="round-result-closed-hand">
                  {closedHand.map((tile) => (
                    <div key={tile.id} className="pov-bottom small">
                      <TileComponent tile={tile} size="small" isWild={isWildTile(tile)} />
                    </div>
                  ))}

                  {result.winTile && (
                    <div className="pov-bottom small round-result-win-tile">
                      <TileComponent tile={result.winTile} size="small" isWild={isWildTile(result.winTile)} />
                    </div>
                  )}
                </div>

                {winningMelds.length > 0 && (
                  <div className="round-result-melds-divider">
                    <OpenMelds melds={winningMelds} isWildTile={isWildTile} />
                  </div>
                )}

                {flowers.length > 0 && (
                  <div className="round-result-melds-divider">
                    {flowers.map((tile) => (
                      <div key={`fl-${tile.id}`} className="pov-bottom small">
                        <TileComponent tile={tile} size="small" isWild={isWildTile(tile)} />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {breakdown.length > 0 && (
              <div className="round-result-panel">
                <div className="round-result-breakdown-scroll">
                  <div className="round-result-breakdown-grid">
                    {breakdown.map((entry, index) => (
                      <div key={`${entry.name}-${index}`} className="round-result-breakdown-item">
                        <div className="round-result-breakdown-name">{entry.name}</div>
                        <div className="round-result-breakdown-points">+{entry.points}</div>
                      </div>
                    ))}

                    <div className="round-result-breakdown-total-row">
                      <div>Total</div>
                      <div>{result.totalScore}</div>
                    </div>
                  </div>
                </div>
              </div>
            )}

            <div className="round-result-panel round-result-panel-plain">
              <div className="round-result-payout-grid">
                {payouts.map((payout) => (
                  <div
                    key={`${payout.seat}-${payout.label}`}
                    className={`round-result-payout-cell ${payout.amount > 0 ? 'round-result-payout-positive' : 'round-result-payout-negative'}`}
                  >
                    <div className="round-result-payout-seat">{payout.label}</div>
                    <div className="round-result-payout-amount">
                      {payout.amount > 0 ? '+' : ''}
                      {payout.amount}
                    </div>
                    {payout.readyLabel && (
                      <div className={`round-result-payout-ready ${payout.readyActive ? 'round-result-payout-ready-on' : ''}`}>
                        {payout.readyLabel}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </>
        )}

        {result.actions && (
          <div className="round-result-actions">
            {result.actions}
          </div>
        )}
      </div>
    </div>
  )
}
