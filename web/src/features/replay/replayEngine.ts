import { getTileName } from '../../utils/tileUtils'
import type { Paipu, PaipuRound } from './replayTypes'
import { tileObjectFromId } from './replayTypes'

export interface ReplayTile {
  id: number
  suit: number
  value: number
}

export interface ReplayMeld {
  type: string
  tiles: ReplayTile[]
  from: number // discarder seat, -1 for closed
  addedTile?: number // for an upgraded pon (risky kong): id of the added 4th tile
}

export interface ReplayPlayerState {
  seat: number
  hand: ReplayTile[]
  drawnTileId: number | null
  discards: ReplayTile[]
  melds: ReplayMeld[]
  flowers: ReplayTile[]
  score: number
}

export interface ReplayState {
  players: [ReplayPlayerState, ReplayPlayerState, ReplayPlayerState, ReplayPlayerState]
  wildTiles: ReplayTile[]
  activeDiscard: ReplayTile | null
  activeSeat: number
  roundNum: number
  actionIndex: number
  totalActions: number
  isRoundEnd: boolean
  result: PaipuRound['result']
}

export class ReplayEngine {
  paipu: Paipu
  private roundIndex: number = 0
  private actionIndex: number = -1

  constructor(paipu: Paipu) {
    this.paipu = paipu
  }

  get currentRound(): PaipuRound {
    return this.paipu.rounds[this.roundIndex]
  }

  get totalRounds(): number {
    return this.paipu.rounds.length
  }

  get currentRoundIndex(): number {
    return this.roundIndex
  }

  jumpToRound(index: number) {
    if (index < 0 || index >= this.paipu.rounds.length) return
    this.roundIndex = index
    this.actionIndex = -1
  }

  stepForward(): boolean {
    const round = this.currentRound
    if (this.actionIndex >= round.actions.length - 1) return false
    this.actionIndex++
    return true
  }

  stepBackward(): boolean {
    if (this.actionIndex < 0) return false
    this.actionIndex--
    return true
  }

  jumpToStart() {
    this.actionIndex = -1
  }

  jumpToEnd() {
    this.actionIndex = this.currentRound.actions.length - 1
  }

  /** Jump to a specific round and step forward to a specific action index within it (e.g. a review-panel deep link). */
  jumpToAction(roundIndex: number, actionIndex: number) {
    this.jumpToRound(roundIndex)
    while (this.actionIndex < actionIndex && this.stepForward()) {
      // advance one action at a time until we reach actionIndex (or run out of actions)
    }
  }

  getActionDescription(lang: 'en' | 'zh' = 'en'): string {
    if (this.actionIndex < 0) return lang === 'zh' ? '发牌' : 'Deal'
    const action = this.currentRound.actions[this.actionIndex]
    const playerName = this.paipu.players[action.seat]?.name ?? (lang === 'zh' ? `${action.seat}号座位` : `Seat ${action.seat}`)
    if (lang === 'zh') {
      switch (action.act) {
        case 'draw': return `${playerName} 摸牌`
        case 'discard': return `${playerName} 打出 ${getTileName(tileObjectFromId(action.tile as number))}`
        case 'chii': return `${playerName} 吃`
        case 'pon': return `${playerName} 碰`
        case 'okan': return `${playerName} 明杠`
        case 'ckan': return `${playerName} 暗杠`
        case 'ukan': return `${playerName} 加杠`
        case 'flower': return `${playerName} 补花`
        case 'tsumo': return `${playerName} 自摸`
        case 'ron': return `${playerName} 荣和`
        case 'haitei': return `${playerName} 接受海底牌`
        case 'haiteiRefuse': return `${playerName} 拒绝海底牌`
        default: return action.act
      }
    }
    switch (action.act) {
      case 'draw': return `${playerName} draws`
      case 'discard': {
        const t = tileObjectFromId(action.tile as number)
        return `${playerName} discards ${getTileName(t)}`
      }
      case 'chii': return `${playerName} calls Chii`
      case 'pon': return `${playerName} calls Pon`
      case 'okan': return `${playerName} calls Open Kan`
      case 'ckan': return `${playerName} declares Closed Kan`
      case 'ukan': return `${playerName} upgrades to Kan`
      case 'flower': return `${playerName} reveals Flower`
      case 'tsumo': return `${playerName} wins (Tsumo)`
      case 'ron': return `${playerName} wins (Ron)`
      case 'haitei': return `${playerName} accepts Haitei`
      case 'haiteiRefuse': return `${playerName} refuses Haitei`
      default: return action.act
    }
  }

  getState(): ReplayState {
    const round = this.currentRound

    const players = [0, 1, 2, 3].map(seat => ({
      seat,
      hand: round.deals[seat].map(tileObjectFromId),
      drawnTileId: null,
      discards: [] as ReplayTile[],
      melds: [] as ReplayMeld[],
      flowers: [] as ReplayTile[],
      score: round.startingScores[seat],
    })) as [ReplayPlayerState, ReplayPlayerState, ReplayPlayerState, ReplayPlayerState]

    // Apply initial flowers
    for (const fl of (round.initialFlowers ?? [])) {
      const p = players[fl.seat]
      const idx = p.hand.findIndex(t => t.id === fl.flower)
      if (idx >= 0) p.hand.splice(idx, 1)
      p.flowers.push(tileObjectFromId(fl.flower))
      p.hand.push(tileObjectFromId(fl.replacement))
    }

    let activeDiscard: ReplayTile | null = null
    let activeSeat = round.dealer
    let isRoundEnd = false

    for (let i = 0; i <= this.actionIndex && i < round.actions.length; i++) {
      const action = round.actions[i]
      const p = players[action.seat]
      activeSeat = action.seat

      switch (action.act) {
        case 'draw':
        case 'haitei':
          p.hand.push(tileObjectFromId(action.tile as number))
          p.drawnTileId = action.tile as number
          activeDiscard = null
          break

        case 'discard':
          removeFromHand(p.hand, action.tile as number)
          p.drawnTileId = null
          p.discards.push(tileObjectFromId(action.tile as number))
          activeDiscard = tileObjectFromId(action.tile as number)
          break

        // Every steal-from-discard claim: the claimed tiles leave the hand, the
        // discarder's last discard is taken, and the two form an open meld.
        case 'chii':
        case 'pon':
        case 'okan': {
          p.drawnTileId = null
          for (const tid of (action.tiles ?? [])) {
            removeFromHand(p.hand, tid)
          }
          const fromP = players[action.from as number]
          if (fromP.discards.length > 0) {
            const stolen = fromP.discards.pop()!
            const meldTiles = [...(action.tiles ?? []).map(tileObjectFromId), stolen]
            // An open kong is 'okan' in the paipu but renders as a kan meld.
            const meldType = action.act === 'okan' ? 'kan' : action.act
            p.melds.push({ type: meldType, tiles: meldTiles, from: action.from as number })
          }
          activeDiscard = null
          break
        }

        case 'ckan': {
          p.drawnTileId = null
          for (const tid of (action.tiles ?? [])) {
            removeFromHand(p.hand, tid)
          }
          p.melds.push({ type: 'kan', tiles: (action.tiles ?? []).map(tileObjectFromId), from: -1 })
          activeDiscard = null
          break
        }

        case 'ukan': {
          p.drawnTileId = null
          removeFromHand(p.hand, action.tile as number)
          const ponIdx = p.melds.findIndex(m =>
            m.type === 'pon' && m.tiles.some(t => {
              const upgraded = tileObjectFromId(action.tile as number)
              return t.suit === upgraded.suit && t.value === upgraded.value
            })
          )
          if (ponIdx >= 0) {
            p.melds[ponIdx].type = 'kan'
            p.melds[ponIdx].tiles.push(tileObjectFromId(action.tile as number))
            p.melds[ponIdx].addedTile = action.tile as number
          }
          activeDiscard = null
          break
        }

        case 'flower':
          p.drawnTileId = null
          removeFromHand(p.hand, action.tile as number)
          p.flowers.push(tileObjectFromId(action.tile as number))
          break

        case 'tsumo':
          p.drawnTileId = null
          isRoundEnd = true
          activeDiscard = null
          break

        case 'ron': {
          p.drawnTileId = null
          const fromP = players[action.from as number]
          if (fromP.discards.length > 0) fromP.discards.pop()
          isRoundEnd = true
          activeDiscard = null
          break
        }

        case 'haiteiRefuse':
          p.drawnTileId = null
          isRoundEnd = true
          break
      }
    }

    let result = null
    if (isRoundEnd && round.result) {
      result = round.result
      for (let i = 0; i < 4; i++) {
        players[i].score += round.result.scoreChanges[i]
      }
    }

    return {
      players,
      wildTiles: (round.wildTiles ?? []).map(t => ({ id: t.id, suit: t.suit, value: t.value })),
      activeDiscard,
      activeSeat,
      roundNum: round.round,
      actionIndex: this.actionIndex,
      totalActions: round.actions.length,
      isRoundEnd,
      result,
    }
  }
}

function removeFromHand(hand: ReplayTile[], tileId: number) {
  const idx = hand.findIndex(t => t.id === tileId)
  if (idx >= 0) hand.splice(idx, 1)
}
