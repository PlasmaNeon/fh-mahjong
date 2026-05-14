import { memo, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import type { ReactNode } from 'react'
import { motion } from 'framer-motion'
import { getSuitOrder, getTileName, getTileSvgName } from '../utils/tileUtils'

export type SeatLaneDirection = 'bottom' | 'right' | 'top' | 'left'

export type TileLike = {
  id: number
  suit: number
  value: number
}

export type MeldLike = {
  tiles: TileLike[]
  calledTileId?: number | null
  calledDirection?: number | null
}

export type PlayerTableView = {
  seat: number
  seatWind?: number
  closedHand?: TileLike[]
  handBackCount?: number
  showClosedHand?: boolean
  drawnTileId?: number | null
  openMelds?: MeldLike[]
  flowerMelds?: TileLike[]
  discards?: TileLike[]
  shantenLabel?: string | null
}

export type HudChip = {
  label: string
  tone?: 'default' | 'danger'
}

export type RoundResultBreakdownEntry = {
  name: string
  points: number
}

export type RoundResultPayout = {
  seat: number
  label: string
  amount: number
  readyLabel?: string | null
  readyActive?: boolean
}

export type RoundResultView = {
  isDraw: boolean
  winType?: 'tsumo' | 'ron'
  winnerLabel?: string
  discarderLabel?: string | null
  closedHand?: TileLike[]
  winTile?: TileLike | null
  winningMelds?: MeldLike[]
  flowers?: TileLike[]
  breakdown?: RoundResultBreakdownEntry[]
  totalScore?: number
  payouts?: RoundResultPayout[]
  actions?: ReactNode
}

type TileComponentProps = {
  tile: TileLike
  isInteractive?: boolean
  size?: 'normal' | 'small'
  noGlow?: boolean
  isWild?: boolean
  onDiscard?: (tile: TileLike) => void
}

type DiscardLaneProps = {
  direction: SeatLaneDirection
  discards: TileLike[]
  isWildTile?: (tile: TileLike) => boolean
  animateDiscardTileIds?: Set<number>
  callableDiscardTileId?: number | null
  hiddenTileIds?: Set<number>
}

export type SeatLaneProps = {
  direction: SeatLaneDirection
  player: PlayerTableView
  canDiscard?: boolean
  onDiscard?: (tile: TileLike) => void
  isWildTile?: (tile: TileLike) => boolean
  hiddenTileIds?: Set<number>
}

type TableBoardProps = {
  viewSeat: number
  players: PlayerTableView[]
  activeSeat: number
  wildTiles?: TileLike[]
  hudChips?: HudChip[]
  actionBar?: ReactNode
  canDiscardSeat?: number | null
  onDiscard?: (tile: TileLike) => void
  isWildTile?: (tile: TileLike) => boolean
  animateDiscardTileIds?: Set<number>
  callableDiscard?: { seat: number; tileId: number } | null
}

type TileMotionRole = 'hand' | 'drawn' | 'discard'

type TileMotionDescriptor = {
  tile: TileLike
  direction: SeatLaneDirection
  role: TileMotionRole
}

type TileRect = {
  left: number
  top: number
  width: number
  height: number
}

type FlyingTileAnimation = {
  key: number
  tile: TileLike
  direction: SeatLaneDirection
  fromRect: TileRect
  toRect: TileRect
  isWild: boolean
}

const WIND_KANJI = ['', '東', '南', '西', '北']
const POSITIONS: SeatLaneDirection[] = ['bottom', 'right', 'top', 'left']

export const TileComponent = memo(function TileComponent({
  tile,
  isInteractive = false,
  size = 'normal',
  noGlow = false,
  isWild = false,
  onDiscard,
}: TileComponentProps) {
  const svgName = getTileSvgName(tile)

  return (
    <div
      className={`mahjong-tile ${isWild ? 'wild-tile' : ''} ${isInteractive ? 'interactive' : ''} ${size === 'small' ? 'small' : ''}`}
      onClick={() => isInteractive && onDiscard?.(tile)}
      style={{
        padding: 0,
        border: 'none',
        backgroundColor: 'transparent',
        boxShadow: (isWild && !noGlow) ? '0 0 15px 6px rgba(234, 179, 8, 0.9)' : '1px 1px 3px rgba(0,0,0,0.5)',
        position: 'relative',
      }}
    >
      <img
        src={`/Regular_shortnames/${svgName}`}
        alt={getTileName(tile)}
        style={{ width: '85%', height: '85%', display: 'block', position: 'absolute', top: '7.5%', left: '7.5%', zIndex: 2 }}
        draggable="false"
      />
    </div>
  )
})

export function getSeatDirection(seat: number, viewSeat: number): SeatLaneDirection {
  return POSITIONS[(seat - viewSeat + 4) % 4]
}

function compareTileSortKey(a: TileLike, b: TileLike) {
  const suitA = getSuitOrder(a.suit)
  const suitB = getSuitOrder(b.suit)
  if (suitA !== suitB) return suitA - suitB
  return a.value - b.value
}

function sortTiles(tiles: TileLike[]) {
  return [...tiles].sort((a, b) => {
    const cmp = compareTileSortKey(a, b)
    if (cmp !== 0) return cmp
    return a.id - b.id
  })
}

function insertTileAtRightmostOfGroup(
  order: number[],
  tile: TileLike,
  tileMap: Map<number, TileLike>,
) {
  let insertIdx = order.length
  for (let i = 0; i < order.length; i++) {
    const current = tileMap.get(order[i])
    if (current && compareTileSortKey(tile, current) < 0) {
      insertIdx = i
      break
    }
  }
  order.splice(insertIdx, 0, tile.id)
}

// Positional-stability model: preserve the previous display order wherever
// possible, so same-suit/value tiles never spontaneously swap places.
//   - Single-in / single-out (typical draw→absorb after discard): if the new
//     tile sort-fits at the discarded tile's position, slot it in place.
//     Otherwise, insert at the rightmost position of its suit/value group.
//   - All other deltas (calls, kan with replacement, initial deal): filter
//     removed tiles and insert each added tile at the rightmost of its group.
function computeStableDisplayOrder(
  baseTiles: TileLike[],
  previousOrder: number[] | null,
): number[] {
  const tileMap = new Map(baseTiles.map((t) => [t.id, t]))

  if (!previousOrder) {
    return sortTiles(baseTiles).map((t) => t.id)
  }

  const currentIds = baseTiles.map((t) => t.id)
  const currentIdSet = new Set(currentIds)
  const previousIdSet = new Set(previousOrder)
  const removedIds = previousOrder.filter((id) => !currentIdSet.has(id))
  const addedIds = currentIds.filter((id) => !previousIdSet.has(id))
  const newOrder = previousOrder.filter((id) => currentIdSet.has(id))

  if (removedIds.length === 1 && addedIds.length === 1) {
    const removedId = removedIds[0]
    const addedId = addedIds[0]
    const addedTile = tileMap.get(addedId)
    if (!addedTile) return newOrder
    // After filtering removedId, the slot it occupied becomes `removedPosition`
    // in newOrder (indices < removedPosition are unchanged; the element
    // formerly at removedPosition+1 now sits at removedPosition).
    const removedPosition = previousOrder.indexOf(removedId)
    const leftTile =
      removedPosition > 0 ? tileMap.get(newOrder[removedPosition - 1]) ?? null : null
    const rightTile =
      removedPosition < newOrder.length ? tileMap.get(newOrder[removedPosition]) ?? null : null
    const fits =
      (leftTile == null || compareTileSortKey(leftTile, addedTile) <= 0) &&
      (rightTile == null || compareTileSortKey(addedTile, rightTile) <= 0)
    if (fits) {
      newOrder.splice(removedPosition, 0, addedId)
    } else {
      insertTileAtRightmostOfGroup(newOrder, addedTile, tileMap)
    }
  } else {
    for (const addedId of addedIds) {
      const tile = tileMap.get(addedId)
      if (tile) insertTileAtRightmostOfGroup(newOrder, tile, tileMap)
    }
  }

  return newOrder
}

function tileIdsEqual(left: unknown, right: unknown) {
  if (left == null || right == null) return false
  return String(left) === String(right)
}

function getDrawAnimationOffset(direction: SeatLaneDirection) {
  if (direction === 'bottom') return { x: 0, y: -30 }
  if (direction === 'top') return { x: 0, y: 30 }
  if (direction === 'left') return { x: 30, y: 0 }
  return { x: -30, y: 0 }
}

function getTileRotation(direction: SeatLaneDirection) {
  if (direction === 'right') return -90
  if (direction === 'top') return 180
  if (direction === 'left') return 90
  return 0
}

function toTileRect(rect: DOMRect): TileRect {
  return {
    left: rect.left,
    top: rect.top,
    width: rect.width,
    height: rect.height,
  }
}

function shouldAnimateTileTransfer(previousRole: TileMotionRole, currentRole: TileMotionRole) {
  return (
    ((previousRole === 'hand' || previousRole === 'drawn') && currentRole === 'discard') ||
    (previousRole === 'drawn' && currentRole === 'hand')
  )
}

function reorderMeldTiles(meld: MeldLike) {
  const displayTiles = [...(meld.tiles || [])]
  const calledTileId = meld.calledTileId ?? -1
  const calledDirection = meld.calledDirection ?? 0
  const stolenIdx = displayTiles.findIndex((tile) => tileIdsEqual(tile.id, calledTileId))

  if (stolenIdx !== -1 && calledDirection > 0) {
    const stolen = displayTiles.splice(stolenIdx, 1)[0]
    if (calledDirection === 3) displayTiles.unshift(stolen)
    else if (calledDirection === 1) displayTiles.push(stolen)
    else if (calledDirection === 2) displayTiles.splice(1, 0, stolen)
  }

  return displayTiles
}

function getOrderedOpenMelds(direction: SeatLaneDirection, melds: MeldLike[]) {
  // Preserve the pre-refactor side-seat rail flow from main: right/left rely on
  // their flex direction, while the bottom rail still needs newest melds nearest the hand.
  return direction === 'bottom' ? [...melds].reverse() : [...melds]
}

function FloatingTile({
  animation,
  onComplete,
}: {
  animation: FlyingTileAnimation
  onComplete: () => void
}) {
  const svgName = getTileSvgName(animation.tile)
  const rotation = getTileRotation(animation.direction)

  return createPortal(
    <motion.div
      initial={{
        left: animation.fromRect.left,
        top: animation.fromRect.top,
        width: animation.fromRect.width,
        height: animation.fromRect.height,
      }}
      animate={{
        left: animation.toRect.left,
        top: animation.toRect.top,
        width: animation.toRect.width,
        height: animation.toRect.height,
      }}
      transition={{ duration: 0.22, ease: 'easeInOut' }}
      onAnimationComplete={onComplete}
      style={{
        position: 'fixed',
        pointerEvents: 'none',
        zIndex: 500,
      }}
    >
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <div style={{ width: '100%', height: '100%', transform: `rotate(${rotation}deg)` }}>
          <div
            className={`mahjong-tile ${animation.isWild ? 'wild-tile' : ''}`}
            style={{
              width: '100%',
              height: '100%',
              padding: 0,
              border: 'none',
              backgroundColor: 'transparent',
              boxShadow: animation.isWild ? '0 0 15px 6px rgba(234, 179, 8, 0.9)' : '1px 1px 3px rgba(0,0,0,0.5)',
              position: 'relative',
            }}
          >
            <img
              src={`/Regular_shortnames/${svgName}`}
              alt={getTileName(animation.tile)}
              style={{
                width: '85%',
                height: '85%',
                display: 'block',
                position: 'absolute',
                top: '7.5%',
                left: '7.5%',
                zIndex: 2,
              }}
              draggable="false"
            />
          </div>
        </div>
      </div>
    </motion.div>,
    document.body
  )
}

function DiscardLane({
  direction,
  discards,
  isWildTile = () => false,
  animateDiscardTileIds,
  callableDiscardTileId = null,
  hiddenTileIds,
}: DiscardLaneProps) {
  return (
    <div className={`discard-lane discard-lane--${direction} ${discards.length === 0 ? 'discard-lane--empty' : ''}`}>
      {discards.length === 0 ? (
        <div className="discard-lane__placeholder" aria-hidden="true" />
      ) : (
        discards.map((tile) => {
          const isNewDiscard = animateDiscardTileIds?.has(tile.id) ?? false
          const isCallableDiscard = tileIdsEqual(callableDiscardTileId, tile.id)

          return (
            <motion.div
              key={tile.id}
              initial={isNewDiscard ? { opacity: 0, scale: 0.82 } : false}
              animate={{ opacity: 1, scale: 1 }}
              transition={{
                opacity: { duration: 0.08, ease: 'easeOut' },
                scale: { duration: 0.1, ease: 'easeOut' },
              }}
              className={`discard-lane__tile ${isCallableDiscard ? 'discard-lane__tile--callable' : ''}`}
              style={hiddenTileIds?.has(tile.id) ? { visibility: 'hidden' } : undefined}
            >
              <motion.div
                layout="position"
                transition={{
                  layout: { duration: 0.18, ease: 'easeOut' },
                }}
                className={`pov-${direction} small`}
                data-board-tile-id={tile.id}
                data-board-tile-role="discard"
              >
                <TileComponent tile={tile} size="small" isWild={isWildTile(tile)} noGlow={isCallableDiscard} />
              </motion.div>
            </motion.div>
          )
        })
      )}
    </div>
  )
}

function SeatLane({
  direction,
  player,
  canDiscard = false,
  onDiscard,
  isWildTile = () => false,
  hiddenTileIds,
}: SeatLaneProps) {
  const lastDrawnTileId = useRef<number | null>(null)
  const displayOrderRef = useRef<number[] | null>(null)
  const isBottomSeat = direction === 'bottom'
  const drawMotionOffset = getDrawAnimationOffset(direction)
  const showClosedHand = player.showClosedHand !== false
  const handTiles = player.closedHand || []
  const handBackCount = player.handBackCount ?? handTiles.length
  const openMelds = getOrderedOpenMelds(direction, player.openMelds || [])
  const flowers = player.flowerMelds || []

  const hasDrawnTile = player.drawnTileId != null
  const baseTiles = [...handTiles]
  let drawnTile: TileLike | null = null

  if (hasDrawnTile) {
    const drawnTileIndex = baseTiles.findIndex((tile) => tileIdsEqual(tile.id, player.drawnTileId))
    if (drawnTileIndex !== -1) {
      drawnTile = baseTiles.splice(drawnTileIndex, 1)[0]
    }
  }

  if (drawnTile) {
    lastDrawnTileId.current = drawnTile.id
  }

  const nextDisplayOrder = computeStableDisplayOrder(baseTiles, displayOrderRef.current)
  displayOrderRef.current = nextDisplayOrder
  const baseTileMap = new Map(baseTiles.map((t) => [t.id, t]))
  const sortedBaseTiles = nextDisplayOrder
    .map((id) => baseTileMap.get(id))
    .filter((t): t is TileLike => t != null)

  const renderHandTile = (tile: TileLike, { isCurrentDrawnSlot = false }: { isCurrentDrawnSlot?: boolean } = {}) => {
    const isRecentlyDrawn = isBottomSeat && lastDrawnTileId.current === tile.id && !hasDrawnTile
    const isHiddenByOverlay = hiddenTileIds?.has(tile.id) ?? false

    return (
      <motion.div
        layout={isCurrentDrawnSlot ? false : "position"}
        key={tile.id}
        style={{
          zIndex: isRecentlyDrawn ? 0 : 10,
          visibility: isHiddenByOverlay ? 'hidden' : undefined,
        }}
        transition={{
          layout: {
            duration: isRecentlyDrawn ? 0.15 : 0.25,
            delay: isRecentlyDrawn ? 0.05 : 0,
            ease: 'easeInOut',
          },
        }}
        className={`pov-${direction} ${!isBottomSeat ? 'small' : ''} ${isCurrentDrawnSlot ? 'drawn-tile' : ''}`}
        data-board-tile-id={isCurrentDrawnSlot ? undefined : tile.id}
        data-board-tile-role={isCurrentDrawnSlot ? undefined : 'hand'}
      >
        <TileComponent
          tile={tile}
          isInteractive={canDiscard}
          isWild={isWildTile(tile)}
          onDiscard={onDiscard}
          size={isBottomSeat ? 'normal' : 'small'}
        />
      </motion.div>
    )
  }

  return (
    <div className={`seat-lane-shell seat-lane-shell--${direction}`}>
      <div className={`seat-lane seat-lane--${direction}`}>
        <div className={`seat-lane__closed seat-lane__closed--${direction} ${isBottomSeat ? 'seat-lane__closed--self' : ''}`}>
          <div className={`seat-hand seat-hand--${direction}`}>
            <div className={`seat-hand__tiles seat-hand__tiles--${direction}`}>
              {showClosedHand ? (
                sortedBaseTiles.map((tile) => renderHandTile(tile))
              ) : (
                Array(handBackCount).fill(null).map((_, index) => (
                  <div key={`back-${index}`} className={`pov-${direction} small`}>
                    <div className="mahjong-tile-back small" />
                  </div>
                ))
              )}
            </div>

            {showClosedHand && drawnTile && (
              <div
                className={`seat-hand__drawn-slot seat-hand__drawn-slot--${direction}`}
                data-board-tile-id={drawnTile.id}
                data-board-tile-role="drawn"
              >
                <motion.div
                  initial={{ opacity: 0, ...drawMotionOffset }}
                  animate={{ opacity: 1, x: 0, y: 0 }}
                  transition={{
                    opacity: { duration: 0.16, ease: 'easeOut' },
                    x: { duration: 0.22, ease: 'easeOut' },
                    y: { duration: 0.22, ease: 'easeOut' },
                  }}
                >
                  {renderHandTile(drawnTile, { isCurrentDrawnSlot: true })}
                </motion.div>
              </div>
            )}
          </div>

          {isBottomSeat && player.shantenLabel && (
            <div className="shanten-indicator">{player.shantenLabel}</div>
          )}
        </div>

        <div className={`seat-lane__gap seat-lane__gap--${direction}`} aria-hidden="true" />

        <div className={`seat-exposed seat-exposed--${direction}`}>
          {flowers.length > 0 && (
            <div className={`seat-flower-rail seat-flower-rail--${direction}`}>
              {flowers.map((tile, flowerIndex) => (
                <div key={`f-${flowerIndex}`} className={`pov-${direction} small`}>
                  <TileComponent tile={tile} size="small" isWild={isWildTile(tile)} />
                </div>
              ))}
            </div>
          )}

          <div className={`seat-meld-rail seat-meld-rail--${direction}`}>
                {openMelds.map((meld, meldIndex) => (
                  <div key={meldIndex} className={`seat-meld-group seat-meld-group--${direction}`}>
                    {reorderMeldTiles(meld).map((tile, tileIndex) => {
                  const isStolen = tileIdsEqual(tile.id, meld.calledTileId)
                  return (
                    <div key={tileIndex} className={`pov-${direction} small ${isStolen ? 'stolen-tile' : ''}`}>
                      <TileComponent tile={tile} size="small" isWild={isWildTile(tile)} />
                    </div>
                  )
                })}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

export function TableBoard({
  viewSeat,
  players,
  activeSeat,
  wildTiles = [],
  hudChips = [],
  actionBar = null,
  canDiscardSeat = null,
  onDiscard,
  isWildTile = () => false,
  animateDiscardTileIds,
  callableDiscard = null,
}: TableBoardProps) {
  const tableRef = useRef<HTMLDivElement | null>(null)
  const previousTileMotionRef = useRef<{
    locations: Map<number, TileMotionDescriptor>
    rects: Map<number, TileRect>
  } | null>(null)
  const animationKeyRef = useRef(0)
  const [flyingTiles, setFlyingTiles] = useState<FlyingTileAnimation[]>([])

  const seatViews = useMemo(() => players.map((player) => ({
    player,
    direction: getSeatDirection(player.seat, viewSeat),
  })), [players, viewSeat])

  useLayoutEffect(() => {
    const currentLocations = new Map<number, TileMotionDescriptor>()

    seatViews.forEach(({ player, direction }) => {
      const showClosedHand = player.showClosedHand !== false
      if (showClosedHand) {
        (player.closedHand || []).forEach((tile) => {
          currentLocations.set(tile.id, {
            tile,
            direction,
            role: tileIdsEqual(tile.id, player.drawnTileId) ? 'drawn' : 'hand',
          })
        })
      }

      (player.discards || []).forEach((tile) => {
        currentLocations.set(tile.id, {
          tile,
          direction,
          role: 'discard',
        })
      })
    })

    const currentRects = new Map<number, TileRect>()
    tableRef.current?.querySelectorAll<HTMLElement>('[data-board-tile-id]').forEach((element) => {
      const tileId = Number(element.dataset.boardTileId)
      if (!Number.isNaN(tileId)) {
        currentRects.set(tileId, toTileRect(element.getBoundingClientRect()))
      }
    })

    const previousSnapshot = previousTileMotionRef.current
    if (previousSnapshot) {
      const nextAnimations: FlyingTileAnimation[] = []

      currentLocations.forEach((currentTile, tileId) => {
        const previousTile = previousSnapshot.locations.get(tileId)
        if (!previousTile) return
        if (previousTile.direction !== currentTile.direction) return
        if (!shouldAnimateTileTransfer(previousTile.role, currentTile.role)) return

        const fromRect = previousSnapshot.rects.get(tileId)
        const toRect = currentRects.get(tileId)
        if (!fromRect || !toRect) return

        const travelDistance = Math.hypot(toRect.left - fromRect.left, toRect.top - fromRect.top)
        if (travelDistance < 4) return

        animationKeyRef.current += 1
        nextAnimations.push({
          key: animationKeyRef.current,
          tile: currentTile.tile,
          direction: currentTile.direction,
          fromRect,
          toRect,
          isWild: isWildTile(currentTile.tile),
        })
      })

      if (nextAnimations.length > 0) {
        setFlyingTiles((existing) => [...existing, ...nextAnimations])
      }
    }

    previousTileMotionRef.current = {
      locations: currentLocations,
      rects: currentRects,
    }
  }, [isWildTile, seatViews])

  const hiddenTileIds = new Set(flyingTiles.map((animation) => animation.tile.id))

  return (
    <div className="mahjong-table" ref={tableRef}>
      {wildTiles.length > 0 && (
        <div className="wild-tile-corner">
          <div className="wild-tile-corner-label">Wild Tile</div>
          <div className="wild-tile-corner-face">
            <TileComponent tile={wildTiles[0]} noGlow />
          </div>
        </div>
      )}

      <div className="center-info text-white text-center">
        {POSITIONS.map((direction, idx) => {
          const seat = players.find((player) => getSeatDirection(player.seat, viewSeat) === POSITIONS[idx])
          if (!seat) return null
          const wind = seat.seatWind ?? 0
          const isActive = seat.seat === activeSeat

          return (
            <div key={direction} className={`center-wind center-wind-${direction} ${isActive ? 'center-wind-active' : ''}`}>
              {WIND_KANJI[wind] || ''}
            </div>
          )
        })}

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
      </div>

      {actionBar}

      {seatViews.map(({ player, direction }) => (
        <DiscardLane
          key={`discard-${player.seat}`}
          direction={direction}
          discards={player.discards || []}
          isWildTile={isWildTile}
          animateDiscardTileIds={animateDiscardTileIds}
          callableDiscardTileId={callableDiscard?.seat === player.seat ? callableDiscard.tileId : null}
          hiddenTileIds={hiddenTileIds}
        />
      ))}

      {seatViews.map(({ player, direction }) => (
        <SeatLane
          key={`seat-${player.seat}`}
          direction={direction}
          player={player}
          canDiscard={direction === 'bottom' && player.seat === canDiscardSeat}
          onDiscard={onDiscard}
          isWildTile={isWildTile}
          hiddenTileIds={hiddenTileIds}
        />
      ))}

      {flyingTiles.map((animation) => (
        <FloatingTile
          key={animation.key}
          animation={animation}
          onComplete={() => {
            setFlyingTiles((existing) => existing.filter((item) => item.key !== animation.key))
          }}
        />
      ))}
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
                    {winningMelds.map((meld, meldIndex) => (
                      <div key={`m-${meldIndex}`} className="seat-meld-group seat-meld-group--bottom">
                    {reorderMeldTiles(meld).map((tile, tileIndex) => {
                          const isStolen = tileIdsEqual(tile.id, meld.calledTileId)
                          return (
                            <div key={tileIndex} className={`pov-bottom small ${isStolen ? 'stolen-tile' : ''}`}>
                              <TileComponent tile={tile} size="small" isWild={isWildTile(tile)} />
                            </div>
                          )
                        })}
                      </div>
                    ))}
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
