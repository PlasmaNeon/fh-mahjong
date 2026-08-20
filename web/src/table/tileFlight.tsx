import { useLayoutEffect, useRef, useState } from 'react'
import type { ReactNode, RefObject } from 'react'
import { createPortal } from 'react-dom'
import { motion } from 'framer-motion'
import { getTileName, getTileSvgName } from '../utils/tileUtils'
import type { PlayerTableView, SeatLaneDirection, TileLike } from './TableScene'
import {
  planTileFlights,
  hiddenHandSlotsByDirection,
  hiddenTileIdsFromAnimations,
  type FlyingTileAnimation,
  type MotionSnapshot,
  type TileMotionDescriptor,
  type TileRect,
} from './tileFlightPlan'
import { tileIdsEqual } from './tileId'

export { tileIdsEqual }

// Shared discard/draw flight animation for every seat.
//
// A tile "flies" when the same tile id moves between roles across renders
// (hand/drawn -> discard, drawn -> hand). The viewer's own hand renders real
// tiles tagged with `data-board-tile-id`, so those transitions are tracked
// directly. Opponents render anonymous face-down backs with no ids, so a
// revealed discard has no tracked source tile. For that case planTileFlights
// flies the tile from the seat's hand region (the `data-seat-hand-origin`
// anchor) instead, so all four players animate identically.

function toTileRect(rect: DOMRect): TileRect {
  return {
    left: rect.left,
    top: rect.top,
    width: rect.width,
    height: rect.height,
  }
}

function getTileRotation(direction: SeatLaneDirection) {
  if (direction === 'right') return -90
  if (direction === 'top') return 180
  if (direction === 'left') return 90
  return 0
}

// Phones in portrait render the whole board CSS-rotated 90deg (the .stage-rotator
// wrapper in index.css, same media query). The flight overlay otherwise portals
// to document.body — outside that transform — so a flying tile would be missing
// the stage's rotation and appear to "rotate twice". When rotated we render the
// overlay inside a wrapper that reproduces .stage-rotator's transform and map
// each screen rect into that wrapper's local coordinate space.
const PHONE_PORTRAIT_QUERY = '(pointer: coarse) and (orientation: portrait) and (max-width: 600px)'

function isPhonePortrait(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia(PHONE_PORTRAIT_QUERY).matches
  )
}

// Inverse of .stage-rotator's `translate(-50%,-50%) rotate(90deg)` about the
// viewport centre. For a 90deg turn it reduces to a rect swap:
//   screen (l,t,w,h) -> local { left: t, top: innerWidth - l - w, width: h, height: w }
// so a tile placed at the returned local rect inside an identically-transformed
// wrapper lands exactly on its settled counterpart, correctly oriented.
function toRotatorLocalRect(rect: TileRect): TileRect {
  return {
    left: rect.top,
    top: window.innerWidth - rect.left - rect.width,
    width: rect.height,
    height: rect.width,
  }
}

function FloatingTile({
  animation,
  positioned,
  onComplete,
}: {
  animation: FlyingTileAnimation
  positioned: 'fixed' | 'absolute'
  onComplete: () => void
}) {
  const svgName = animation.asBack ? 'back.svg' : getTileSvgName(animation.tile)
  const rotation = getTileRotation(animation.direction)

  return (
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
        position: positioned,
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
              alt={animation.asBack ? 'tile back' : getTileName(animation.tile)}
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
    </motion.div>
  )
}

type SeatView = {
  player: PlayerTableView
  direction: SeatLaneDirection
}

type UseTileFlightParams = {
  seatViews: SeatView[]
  isWildTile: (tile: TileLike) => boolean
  tableRef: RefObject<HTMLElement | null>
}

type UseTileFlightResult = {
  // Tile ids currently airborne; their settled positions stay hidden until the
  // flight overlay lands.
  hiddenTileIds: Set<number>
  // Per-direction concealed rail slot indices to blank while a tedashi drawn-back
  // flight is airborne (opponent gap fill).
  hiddenHandSlots: Map<SeatLaneDirection, Set<number>>
  // Portal overlay rendering every in-flight tile.
  flights: ReactNode
}

export function useTileFlight({
  seatViews,
  isWildTile,
  tableRef,
}: UseTileFlightParams): UseTileFlightResult {
  const previousSnapshotRef = useRef<MotionSnapshot | null>(null)
  const animationKeyRef = useRef(0)
  const [flyingTiles, setFlyingTiles] = useState<FlyingTileAnimation[]>([])

  useLayoutEffect(() => {
    const currentLocations = new Map<number, TileMotionDescriptor>()
    // Per-seat tsumogiri flag (was the seat's most recent discard its drawn
    // tile), looked up by the planner using the discarder's direction.
    const fromDrawnByDirection = new Map<SeatLaneDirection, boolean>()

    seatViews.forEach(({ player, direction }) => {
      fromDrawnByDirection.set(direction, player.lastDiscardFromDrawn ?? false)
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

    const currentHandOrigins = new Map<SeatLaneDirection, TileRect>()
    tableRef.current?.querySelectorAll<HTMLElement>('[data-seat-hand-origin]').forEach((element) => {
      const direction = element.dataset.seatHandOrigin as SeatLaneDirection | undefined
      if (!direction) return
      const rect = element.getBoundingClientRect()
      if (rect.width > 0 && rect.height > 0) {
        currentHandOrigins.set(direction, toTileRect(rect))
      }
    })

    const previousSnapshot = previousSnapshotRef.current
    if (previousSnapshot) {
      const nextAnimations = planTileFlights({
        previousSnapshot,
        currentLocations,
        currentRects,
        currentHandOrigins,
        isWildTile,
        startKey: animationKeyRef.current,
        fromDrawnByDirection,
      })

      if (nextAnimations.length > 0) {
        animationKeyRef.current = nextAnimations[nextAnimations.length - 1].key
        setFlyingTiles((existing) => [...existing, ...nextAnimations])
      }
    }

    previousSnapshotRef.current = {
      locations: currentLocations,
      rects: currentRects,
      handOrigins: currentHandOrigins,
    }
  }, [isWildTile, seatViews, tableRef])

  const hiddenTileIds = hiddenTileIdsFromAnimations(flyingTiles)
  const hiddenHandSlots = hiddenHandSlotsByDirection(flyingTiles)

  // In phone-portrait the board is CSS-rotated; render the overlay inside a
  // wrapper with the same transform and feed it rotator-local rects. Otherwise
  // (desktop / iPad / landscape) the overlay stays in viewport space as before.
  const phonePortrait = isPhonePortrait()

  const tileNodes = flyingTiles.map((animation) => (
    <FloatingTile
      key={animation.key}
      animation={
        phonePortrait
          ? {
              ...animation,
              fromRect: toRotatorLocalRect(animation.fromRect),
              toRect: toRotatorLocalRect(animation.toRect),
            }
          : animation
      }
      positioned={phonePortrait ? 'absolute' : 'fixed'}
      onComplete={() => {
        setFlyingTiles((existing) => existing.filter((item) => item.key !== animation.key))
      }}
    />
  ))

  const flights =
    flyingTiles.length === 0
      ? null
      : createPortal(
          phonePortrait ? (
            <div
              style={{
                position: 'fixed',
                top: '50%',
                left: '50%',
                width: '100dvh',
                height: '100dvw',
                transform: 'translate(-50%, -50%) rotate(90deg)',
                transformOrigin: 'center center',
                pointerEvents: 'none',
                zIndex: 500,
              }}
            >
              {tileNodes}
            </div>
          ) : (
            <>{tileNodes}</>
          ),
          document.body,
        )

  return { hiddenTileIds, hiddenHandSlots, flights }
}
