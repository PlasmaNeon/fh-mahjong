import { useEffect, useState } from 'react'

import { getApiUrl, hasConfiguredApiBaseUrl } from '../config'
import { ActionType, MeldDirection } from '../proto/game.ts'
import { getTileName, getTileSvgName } from '../utils/tileUtils'
import {
  buildCalcRequestPayload,
  CalcKongContextKey,
  CalcKongFlags,
  CalcMeldDraft,
  CalcSuccessResponse,
  CalcTileDraft,
  CalcTileValue,
  createMeldDraft,
  createTileDraft,
  expectedClosedHandSize,
  FLOWER_OPTIONS,
  formatTehai,
  formatTile,
  getDirectionLabel,
  getMeldLabel,
  meldRequiredTileCount,
  normalizeCalcErrorResponse,
  normalizeCalcSuccessResponse,
  parseSingleTileInput,
  parseTehaiInput,
  sameTileValue,
  sortTiles,
  TILE_LIBRARY,
  validateCalculatorState,
  validateMeldShape,
  WIND_OPTIONS,
} from './calcHelpers'
import './ledger-theme.css'

type InputErrors = {
  closedHand: string[]
  winTile: string[]
  wildTile: string[]
}

type CollapsedSections = {
  closedHand: boolean
  winTile: boolean
  wildTile: boolean
}

type Lang = 'en' | 'zh'

const UI_TEXT = {
  en: {
    language: '中文',
    title: 'Calculator',
    closedHand: 'Closed hand',
    winTile: 'Win tile',
    wildTile: 'Wild tile',
    expectedCount: 'Expected',
    openMelds: 'open meld(s)',
    apply: 'Apply',
    edit: 'Edit',
    tilePalette: 'Tile palette',
    noClosedHand: 'No tiles in the closed hand yet.',
    noWinTile: 'No win tile selected.',
    noWildTile: 'No wild tile selected.',
    openMeldsTitle: 'Open melds',
    activeMeldPalette: 'Meld palette',
    add: 'Add',
    noOpenMelds: 'No open melds yet.',
    openMeld: 'Meld',
    tiles: 'tiles',
    usePalette: 'Use palette',
    clear: 'Clear',
    remove: 'Remove',
    meldType: 'Type',
    calledDirection: 'Direction',
    calledTile: 'Called tile',
    addTilesFirst: 'Add tiles first',
    meldEmpty: 'Use the palette or change type to start composing.',
    kanContext: 'Kan context',
    noKanContext: 'No extra context',
    roundContext: 'Round context',
    winType: 'Win type',
    tsumo: 'Tsumo',
    ron: 'Ron',
    flowerKong: 'Win by flower replacement',
    seatWind: 'Seat wind',
    prevailingWind: 'Prevailing wind',
    flowerMelds: 'Flower melds',
    calculating: 'Calculating…',
    calculatePoints: 'Calculate',
    noValidationErrors: 'No issues.',
    result: 'Result',
    validHand: 'Valid hand',
    invalidHand: 'Invalid hand',
    awaitingEvaluation: 'Awaiting evaluation',
    totalScore: 'Total score',
    breakdown: 'Breakdown',
    noEntries: 'No scoring entries.',
    submitToSeeResult: 'Submit a hand to see the score.',
    normalizedSummary: 'Normalized request',
    context: 'Context',
    expectedClosedHandLength: 'Expected closed hand',
    none: '—',
    evaluateToCapture: 'Evaluate a hand to see the normalized request.',
    showDebug: 'Show normalized request',
    hideDebug: 'Hide normalized request',
  },
  zh: {
    language: 'English',
    title: '算分器',
    closedHand: '手牌',
    winTile: '和牌',
    wildTile: '搭牌',
    expectedCount: '应有',
    openMelds: '副露',
    apply: '应用',
    edit: '编辑',
    tilePalette: '牌库',
    noClosedHand: '当前还没有手牌。',
    noWinTile: '尚未选择和牌。',
    noWildTile: '尚未选择搭牌。',
    openMeldsTitle: '副露',
    activeMeldPalette: '副露牌库',
    add: '新增',
    noOpenMelds: '当前还没有副露。',
    openMeld: '副露',
    tiles: '张',
    usePalette: '牌库加牌',
    clear: '清空',
    remove: '删除',
    meldType: '类型',
    calledDirection: '来源',
    calledTile: '被叫牌',
    addTilesFirst: '请先加入牌张',
    meldEmpty: '使用上方牌库，或先切换类型开始编辑。',
    kanContext: '杠牌上下文',
    noKanContext: '无额外上下文',
    roundContext: '牌局上下文',
    winType: '和牌方式',
    tsumo: '自摸',
    ron: '点炮',
    flowerKong: '补花自摸',
    seatWind: '门风',
    prevailingWind: '圈风',
    flowerMelds: '花牌',
    calculating: '计算中…',
    calculatePoints: '计算分数',
    noValidationErrors: '无校验错误。',
    result: '结果',
    validHand: '可和牌',
    invalidHand: '不可和牌',
    awaitingEvaluation: '等待计算',
    totalScore: '总分',
    breakdown: '明细',
    noEntries: '当前没有返回算分条目。',
    submitToSeeResult: '提交一次计算请求后，这里会显示结果。',
    normalizedSummary: '标准化请求',
    context: '上下文',
    expectedClosedHandLength: '应有手牌张数',
    none: '—',
    evaluateToCapture: '进行一次计算后，这里会显示标准化调试摘要。',
    showDebug: '显示标准化请求',
    hideDebug: '隐藏标准化请求',
  },
} as const

const KONG_FLAG_OPTIONS: Array<{ key: keyof CalcKongFlags; label: string }> = [
  { key: 'hasBuddingDirectKong', label: 'Budding Direct Kong' },
  { key: 'hasBloomingDirectKong', label: 'Blooming Direct Kong' },
  { key: 'hasBuddingClosedKong', label: 'Budding Closed Kong' },
  { key: 'hasBloomingClosedKong', label: 'Blooming Closed Kong' },
  { key: 'hasBuddingRiskyKong', label: 'Budding Risky Kong' },
  { key: 'hasBloomingRiskyKong', label: 'Blooming Risky Kong' },
]

const MELD_TYPE_OPTIONS = [
  { value: ActionType.ACTION_CHII, label: 'Chii' },
  { value: ActionType.ACTION_PON, label: 'Pon' },
  { value: ActionType.ACTION_KAN, label: 'Kan' },
]

const MELD_DIRECTION_OPTIONS = [
  { value: MeldDirection.MELD_DIRECTION_UNKNOWN, label: 'Self' },
  { value: MeldDirection.MELD_DIRECTION_RIGHT, label: 'Right' },
  { value: MeldDirection.MELD_DIRECTION_ACROSS, label: 'Across' },
  { value: MeldDirection.MELD_DIRECTION_LEFT, label: 'Left' },
]

// ─── Tile component ───

function CalcTile({
  tile,
  onClick,
  size = 'normal',
  selected = false,
  dimmed = false,
}: {
  tile: CalcTileValue
  onClick?: () => void
  size?: 'normal' | 'small' | 'palette'
  selected?: boolean
  dimmed?: boolean
}) {
  const svgName = getTileSvgName(tile)
  const cls = [
    'ldg-tile',
    size === 'small' ? 'ldg-tile--sm' : '',
    size === 'palette' ? 'ldg-tile--pal' : '',
    selected ? 'ldg-tile--sel' : '',
    dimmed ? 'ldg-tile--dim' : '',
    !onClick ? 'ldg-tile--static' : '',
  ].filter(Boolean).join(' ')

  return (
    <button
      type="button"
      className={cls}
      onClick={onClick}
      title={getTileName(tile)}
    >
      <img src={`/Regular_shortnames/${svgName}`} alt={getTileName(tile)} draggable="false" />
    </button>
  )
}

// ─── Tile row ───

function TileRow({ tiles, emptyLabel, onTileClick }: {
  tiles: CalcTileDraft[]
  emptyLabel: string
  onTileClick: (tileId: string) => void
}) {
  if (tiles.length === 0) {
    return (
      <div className="ldg-tile-row ldg-tile-row--empty">
        <span className="ldg-note" style={{ marginTop: 0 }}>{emptyLabel}</span>
      </div>
    )
  }
  return (
    <div className="ldg-tile-row">
      {tiles.map((tile) => (
        <CalcTile key={tile.id} tile={tile} onClick={() => onTileClick(tile.id)} />
      ))}
    </div>
  )
}

// ─── Palette grid ───

function PaletteGrid({ onTileClick, selectedTile = null, dimSelected = false }: {
  onTileClick: (tile: CalcTileValue) => void
  selectedTile?: CalcTileDraft | null
  dimSelected?: boolean
}) {
  return (
    <div className="ldg-palette-grid">
      {TILE_LIBRARY.map((tile) => {
        const isSelectedPaletteTile = sameTileValue(tile, selectedTile)
        return (
          <CalcTile
            key={formatTile(tile)}
            tile={tile}
            onClick={() => onTileClick(tile)}
            size="palette"
            selected={isSelectedPaletteTile}
            dimmed={dimSelected && isSelectedPaletteTile}
          />
        )
      })}
    </div>
  )
}

// ─── Helpers ───

function parseErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Unknown calculator error.'
}

async function readResponsePayload(response: Response): Promise<unknown> {
  const contentType = response.headers.get('content-type') ?? ''
  const text = await response.text()
  if (!text.trim()) return null
  if (!contentType.includes('application/json')) {
    throw new Error('Calculator endpoint returned a non-JSON response. Check the deployed API base URL.')
  }
  try {
    return JSON.parse(text) as unknown
  } catch {
    throw new Error('Calculator endpoint returned invalid JSON. Check the deployed API base URL.')
  }
}

function getMeldLabelForLang(type: ActionType, lang: Lang): string {
  const label = getMeldLabel(type)
  if (lang === 'en') return label
  switch (label) {
    case 'Chii': return '吃'
    case 'Pon': return '碰'
    case 'Kan': return '杠'
    default: return label
  }
}

function getDirectionLabelForLang(direction: MeldDirection, lang: Lang): string {
  const label = getDirectionLabel(direction)
  if (lang === 'en') return label
  switch (label) {
    case 'Self': return '自家'
    case 'Right': return '右家'
    case 'Across': return '对家'
    case 'Left': return '左家'
    default: return label
  }
}

function getWindLabelForLang(value: number, lang: Lang): string {
  const map = lang === 'zh'
    ? { 1: '东', 2: '南', 3: '西', 4: '北' }
    : { 1: 'East', 2: 'South', 3: 'West', 4: 'North' }
  return map[value as 1 | 2 | 3 | 4] ?? String(value)
}

function getKongFlagLabelForLang(key: keyof CalcKongFlags, lang: Lang): string {
  const zh: Record<keyof CalcKongFlags, string> = {
    hasBuddingDirectKong: '直杠不开花',
    hasBloomingDirectKong: '直杠开花',
    hasBuddingClosedKong: '暗杠不开花',
    hasBloomingClosedKong: '暗杠开花',
    hasBuddingRiskyKong: '风险杠不开花',
    hasBloomingRiskyKong: '风险杠开花',
    hasBloomingFlowerKong: '花杠杠开',
  }
  const option = KONG_FLAG_OPTIONS.find((item) => item.key === key)
  return lang === 'zh' ? zh[key] : option?.label ?? key
}

function localizeDebugValue(value: string, lang: Lang): string {
  if (lang === 'en' || !value) return value
  const translations: Record<string, string> = {
    East: '东', South: '南', West: '西', North: '北',
    tsumo: '自摸', ron: '点炮',
    chii: '吃', pon: '碰', kan: '杠',
    right: '右家', across: '对家', left: '左家',
    'Budding Direct Kong': '直杠不开花',
    'Blooming Direct Kong': '直杠开花',
    'Budding Closed Kong': '暗杠不开花',
    'Blooming Closed Kong': '暗杠开花',
    'Budding Risky Kong': '风险杠不开花',
    'Blooming Risky Kong': '风险杠开花',
    'Blooming Flower Kong': '花杠杠开',
  }
  return translations[value] ?? value
}

// ─── Main page ───

export default function Calc() {
  const [lang, setLang] = useState<Lang>('en')
  const [closedHand, setClosedHand] = useState<CalcTileDraft[]>([])
  const [winTile, setWinTile] = useState<CalcTileDraft | null>(null)
  const [wildTile, setWildTile] = useState<CalcTileDraft | null>(null)
  const [openMelds, setOpenMelds] = useState<CalcMeldDraft[]>([])
  const [flowerMelds, setFlowerMelds] = useState<number[]>([])
  const [isTsumo, setIsTsumo] = useState(true)
  const [hasBloomingFlowerKong, setHasBloomingFlowerKong] = useState(false)
  const [seatWind, setSeatWind] = useState(1)
  const [prevailingWind, setPrevailingWind] = useState(1)
  const [activeMeldId, setActiveMeldId] = useState<string | null>(null)
  const [closedHandInput, setClosedHandInput] = useState('')
  const [winTileInput, setWinTileInput] = useState('')
  const [wildTileInput, setWildTileInput] = useState('')
  const [inputErrors, setInputErrors] = useState<InputErrors>({ closedHand: [], winTile: [], wildTile: [] })
  const [serverErrors, setServerErrors] = useState<string[]>([])
  const [result, setResult] = useState<CalcSuccessResponse | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [collapsedSections, setCollapsedSections] = useState<CollapsedSections>({
    closedHand: false,
    winTile: false,
    wildTile: false,
  })
  const [showDebug, setShowDebug] = useState(false)

  useEffect(() => { setClosedHandInput(formatTehai(closedHand)) }, [closedHand])
  useEffect(() => { setWinTileInput(formatTile(winTile)) }, [winTile])
  useEffect(() => { setWildTileInput(formatTile(wildTile)) }, [wildTile])

  const validationErrors = validateCalculatorState({
    closedHand, winTile, wildTile, openMelds, flowerMelds, seatWind, prevailingWind,
  })

  const clearServerState = () => { setResult(null); setServerErrors([]) }

  const applyClosedHandInput = (): CalcTileDraft[] | null => {
    const parsed = parseTehaiInput(closedHandInput)
    if (parsed.errors.length > 0) {
      setInputErrors((current) => ({ ...current, closedHand: parsed.errors }))
      return null
    }
    const nextClosedHand = sortTiles(parsed.tiles.map(createTileDraft))
    setClosedHand(nextClosedHand)
    setInputErrors((current) => ({ ...current, closedHand: [] }))
    setCollapsedSections((current) => ({ ...current, closedHand: true }))
    clearServerState()
    return nextClosedHand
  }

  const applyWinTileInput = (): CalcTileDraft | null | undefined => {
    const parsed = parseSingleTileInput(winTileInput)
    if (parsed.errors.length > 0) {
      setInputErrors((current) => ({ ...current, winTile: parsed.errors }))
      return undefined
    }
    const nextWinTile = parsed.tile ? createTileDraft(parsed.tile) : null
    setWinTile(nextWinTile)
    setInputErrors((current) => ({ ...current, winTile: [] }))
    setCollapsedSections((current) => ({ ...current, winTile: true }))
    clearServerState()
    return nextWinTile
  }

  const applyWildTileInput = (): CalcTileDraft | null | undefined => {
    const parsed = parseSingleTileInput(wildTileInput)
    if (parsed.errors.length > 0) {
      setInputErrors((current) => ({ ...current, wildTile: parsed.errors }))
      return undefined
    }
    const nextWildTile = parsed.tile ? createTileDraft(parsed.tile) : null
    setWildTile(nextWildTile)
    setInputErrors((current) => ({ ...current, wildTile: [] }))
    setCollapsedSections((current) => ({ ...current, wildTile: true }))
    clearServerState()
    return nextWildTile
  }

  const addTileToClosedHand = (tile: CalcTileValue) => {
    clearServerState()
    setClosedHand((current) => sortTiles([...current, createTileDraft(tile)]))
  }

  const addTileToMeld = (meldId: string, tile: CalcTileValue) => {
    clearServerState()
    setOpenMelds((current) =>
      current.map((meld) => {
        if (meld.id !== meldId) return meld
        if (meld.tiles.length >= meldRequiredTileCount(meld.type)) return meld
        return { ...meld, tiles: [...meld.tiles, createTileDraft(tile)] }
      }),
    )
  }

  const removeClosedHandTile = (tileId: string) => {
    setClosedHand((current) => current.filter((tile) => tile.id !== tileId))
    clearServerState()
  }

  const removeMeldTile = (meldId: string, tileId: string) => {
    setOpenMelds((current) =>
      current.map((meld) => {
        if (meld.id !== meldId) return meld
        const nextTiles = meld.tiles.filter((tile: CalcTileDraft) => tile.id !== tileId)
        const nextCalledTileIndex = nextTiles.length === 0 ? 0 : Math.min(meld.calledTileIndex, nextTiles.length - 1)
        return { ...meld, tiles: nextTiles, calledTileIndex: nextCalledTileIndex }
      }),
    )
    clearServerState()
  }

  const addMeld = (type: ActionType) => {
    const nextMeld = createMeldDraft(type)
    setOpenMelds((current) => [...current, nextMeld])
    setActiveMeldId(nextMeld.id)
    clearServerState()
  }

  const updateMeldType = (meldId: string, type: ActionType) => {
    setOpenMelds((current) =>
      current.map((meld) => {
        if (meld.id !== meldId) return meld
        const requiredCount = meldRequiredTileCount(type)
        const nextTiles = meld.tiles.slice(0, requiredCount)
        const nextCalledTileIndex = nextTiles.length === 0 ? 0 : Math.min(meld.calledTileIndex, nextTiles.length - 1)
        return {
          ...meld, type, tiles: nextTiles, calledTileIndex: nextCalledTileIndex,
          calledDirection: type === ActionType.ACTION_CHII ? MeldDirection.MELD_DIRECTION_LEFT : meld.calledDirection,
          kongContext: type === ActionType.ACTION_KAN ? meld.kongContext : '',
        }
      }),
    )
    clearServerState()
  }

  const updateMeldDirection = (meldId: string, direction: MeldDirection) => {
    setOpenMelds((current) =>
      current.map((meld) => (meld.id === meldId ? { ...meld, calledDirection: direction } : meld)),
    )
    clearServerState()
  }

  const updateMeldCalledTileIndex = (meldId: string, calledTileIndex: number) => {
    setOpenMelds((current) =>
      current.map((meld) => (meld.id === meldId ? { ...meld, calledTileIndex } : meld)),
    )
    clearServerState()
  }

  const clearMeld = (meldId: string) => {
    setOpenMelds((current) =>
      current.map((meld) => (
        meld.id === meldId
          ? { ...meld, tiles: [], calledTileIndex: 0, kongContext: meld.type === ActionType.ACTION_KAN ? '' : meld.kongContext }
          : meld
      )),
    )
    clearServerState()
  }

  const removeMeld = (meldId: string) => {
    const nextOpenMelds = openMelds.filter((meld) => meld.id !== meldId)
    setOpenMelds(nextOpenMelds)
    setActiveMeldId((current) => (current === meldId ? nextOpenMelds[0]?.id ?? null : current))
    clearServerState()
  }

  const toggleFlower = (value: number) => {
    setFlowerMelds((current) =>
      current.includes(value)
        ? current.filter((item) => item !== value)
        : [...current, value].sort((left, right) => left - right),
    )
    clearServerState()
  }

  const updateMeldKongContext = (meldId: string, value: CalcKongContextKey) => {
    setOpenMelds((current) =>
      current.map((meld) => {
        if (meld.id !== meldId || meld.type !== ActionType.ACTION_KAN) return meld
        const isClosedKong = value === 'hasBuddingClosedKong' || value === 'hasBloomingClosedKong'
        return {
          ...meld, kongContext: value,
          calledDirection: isClosedKong ? MeldDirection.MELD_DIRECTION_UNKNOWN : meld.calledDirection,
        }
      }),
    )
    clearServerState()
  }

  const handleCalculate = async () => {
    const nextClosedHand = applyClosedHandInput()
    const nextWinTile = applyWinTileInput()
    const nextWildTile = applyWildTileInput()

    if (nextClosedHand === null || nextWinTile === undefined || nextWildTile === undefined) return

    const effectiveClosedHand = nextClosedHand
    const effectiveWinTile = nextWinTile
    const effectiveWildTile = nextWildTile

    const nextValidationErrors = validateCalculatorState({
      closedHand: effectiveClosedHand,
      winTile: effectiveWinTile ?? null,
      wildTile: effectiveWildTile ?? null,
      openMelds, flowerMelds, seatWind, prevailingWind,
    })

    if (nextValidationErrors.length > 0) {
      setServerErrors([])
      setResult(null)
      return
    }

    const payload = buildCalcRequestPayload({
      closedHand: effectiveClosedHand,
      winTile: effectiveWinTile ?? null,
      wildTile: effectiveWildTile ?? null,
      openMelds, flowerMelds, seatWind, prevailingWind, isTsumo, hasBloomingFlowerKong,
    })

    setIsSubmitting(true)
    setServerErrors([])

    try {
      const response = await fetch(getApiUrl('/api/v1/tools/calc'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })

      if (!hasConfiguredApiBaseUrl() && window.location.hostname.endsWith('vercel.app')) {
        const contentType = response.headers.get('content-type') ?? ''
        if (contentType.includes('text/html')) {
          throw new Error('Calculator backend is not configured for this Vercel deploy. Set VITE_API_BASE_URL to your public backend.')
        }
      }

      const responsePayload = await readResponsePayload(response)

      if (!response.ok) {
        const errorPayload = normalizeCalcErrorResponse(responsePayload)
        setResult(null)
        setServerErrors(errorPayload.errors ?? ['Calculator request failed.'])
        return
      }

      const successPayload = normalizeCalcSuccessResponse(responsePayload)
      setResult(successPayload)
    } catch (error) {
      setResult(null)
      setServerErrors([parseErrorMessage(error)])
    } finally {
      setIsSubmitting(false)
    }
  }

  const combinedErrors = [...inputErrors.closedHand, ...inputErrors.winTile, ...inputErrors.wildTile, ...serverErrors]
  const allErrors = [...combinedErrors, ...validationErrors]
  const expectedHandLength = expectedClosedHandSize(openMelds.length)
  const text = UI_TEXT[lang]

  return (
    <div className="ledger-page">
      <div className="ledger-shell ledger-shell--wide">
        <article className="ldg-page">

          {/* Header */}
          <div className="ldg-page-head">
            <div>
              <h1 className="ldg-page-head__title">
                {text.title}
                <small>{lang === 'en' ? '奉化算分器' : 'Fenghua Calculator'}</small>
              </h1>
            </div>
            <div className="ldg-page-head__nav">
              <button
                type="button"
                className="ldg-link"
                onClick={() => setLang((current) => (current === 'en' ? 'zh' : 'en'))}
              >
                {text.language}
              </button>
              <a href="/tools/shanten" className="ldg-link">
                {lang === 'en' ? 'Shanten →' : '向听 →'}
              </a>
            </div>
          </div>

          {/* Closed hand */}
          <section className="ldg-section">
            <div className="ldg-section-row">
              <h2 className="ldg-section-title">
                {text.closedHand}
                <small>{text.expectedCount} {expectedHandLength} {text.tiles}</small>
              </h2>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <span className="ldg-section-meta">{closedHand.length} / {expectedHandLength}</span>
                {collapsedSections.closedHand && (
                  <button
                    type="button"
                    className="ldg-link"
                    onClick={() => setCollapsedSections((current) => ({ ...current, closedHand: false }))}
                  >
                    {text.edit}
                  </button>
                )}
              </div>
            </div>

            {!collapsedSections.closedHand && (
              <div className="ldg-input-row">
                <input
                  className="ldg-input"
                  value={closedHandInput}
                  onChange={(event) => setClosedHandInput(event.target.value)}
                  placeholder="1m2m3m 4p5p6p 7s8s9s 3z"
                />
                <button type="button" className="ldg-btn" onClick={applyClosedHandInput}>
                  {text.apply}
                </button>
              </div>
            )}

            <TileRow tiles={closedHand} emptyLabel={text.noClosedHand} onTileClick={removeClosedHandTile} />

            {!collapsedSections.closedHand && (
              <div className="ldg-palette-drawer">
                <div className="ldg-palette-drawer__head">{text.tilePalette}</div>
                <PaletteGrid onTileClick={addTileToClosedHand} />
              </div>
            )}
          </section>

          {/* Win tile + Wild tile */}
          <div className="ldg-grid-2" style={{ marginTop: 'var(--space)' }}>
            {/* Win tile */}
            <div>
              <div className="ldg-section-row" style={{ marginBottom: '0.85rem' }}>
                <h2 className="ldg-section-title">{text.winTile}</h2>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                  {collapsedSections.winTile && winTile && (
                    <CalcTile tile={winTile} onClick={() => { setWinTile(null); clearServerState() }} size="small" />
                  )}
                  {collapsedSections.winTile && (
                    <button
                      type="button"
                      className="ldg-link"
                      onClick={() => setCollapsedSections((current) => ({ ...current, winTile: false }))}
                    >
                      {text.edit}
                    </button>
                  )}
                </div>
              </div>

              {!collapsedSections.winTile && (
                <>
                  <div className="ldg-input-row">
                    <input
                      className="ldg-input"
                      value={winTileInput}
                      onChange={(event) => setWinTileInput(event.target.value)}
                      placeholder="3z"
                    />
                    <button type="button" className="ldg-btn" onClick={applyWinTileInput}>
                      {text.apply}
                    </button>
                  </div>
                  <div className="ldg-palette-drawer">
                    <div className="ldg-palette-drawer__head">{text.tilePalette}</div>
                    <PaletteGrid
                      onTileClick={(tile) => { setWinTile(createTileDraft(tile)); clearServerState() }}
                      selectedTile={winTile}
                    />
                  </div>
                  {!winTile && (
                    <p className="ldg-note">{text.noWinTile}</p>
                  )}
                </>
              )}
            </div>

            {/* Wild tile */}
            <div>
              <div className="ldg-section-row" style={{ marginBottom: '0.85rem' }}>
                <h2 className="ldg-section-title">{text.wildTile}</h2>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                  {collapsedSections.wildTile && wildTile && (
                    <CalcTile tile={wildTile} onClick={() => { setWildTile(null); clearServerState() }} size="small" selected />
                  )}
                  {collapsedSections.wildTile && (
                    <button
                      type="button"
                      className="ldg-link"
                      onClick={() => setCollapsedSections((current) => ({ ...current, wildTile: false }))}
                    >
                      {text.edit}
                    </button>
                  )}
                </div>
              </div>

              {!collapsedSections.wildTile && (
                <>
                  <div className="ldg-input-row">
                    <input
                      className="ldg-input"
                      value={wildTileInput}
                      onChange={(event) => setWildTileInput(event.target.value)}
                      placeholder="9s"
                    />
                    <button type="button" className="ldg-btn" onClick={applyWildTileInput}>
                      {text.apply}
                    </button>
                  </div>
                  <div className="ldg-palette-drawer">
                    <div className="ldg-palette-drawer__head">{text.tilePalette}</div>
                    <PaletteGrid
                      onTileClick={(tile) => { setWildTile(createTileDraft(tile)); clearServerState() }}
                      selectedTile={wildTile}
                      dimSelected
                    />
                  </div>
                  {!wildTile && (
                    <p className="ldg-note">{text.noWildTile}</p>
                  )}
                </>
              )}
            </div>
          </div>

          {/* Open melds */}
          <section className="ldg-section">
            <div className="ldg-section-row">
              <h2 className="ldg-section-title">{text.openMeldsTitle}</h2>
              <span className="ldg-section-meta">{openMelds.length}</span>
            </div>

            {openMelds.length === 0 ? (
              <p className="ldg-note">{text.noOpenMelds}</p>
            ) : (
              openMelds.map((meld, index) => {
                const meldError = validateMeldShape(meld)
                const isActive = activeMeldId === meld.id
                return (
                  <div key={meld.id} className={`ldg-meld${isActive ? ' ldg-meld--active' : ''}`}>
                    <div className="ldg-meld__head">
                      <div>
                        <p className="ldg-meld__title">{text.openMeld} {index + 1}</p>
                        <p className="ldg-meld__meta">
                          {meld.tiles.length}/{meldRequiredTileCount(meld.type)} {text.tiles}
                          {' · '}{getDirectionLabelForLang(meld.calledDirection, lang)}
                        </p>
                      </div>
                      <div className="ldg-meld__actions">
                        <button
                          type="button"
                          className={`ldg-btn${isActive ? ' ldg-btn--primary' : ''}`}
                          onClick={() => setActiveMeldId(isActive ? null : meld.id)}
                        >
                          {text.usePalette}
                        </button>
                        <button type="button" className="ldg-btn" onClick={() => clearMeld(meld.id)}>
                          {text.clear}
                        </button>
                        <button type="button" className="ldg-btn ldg-btn--danger" onClick={() => removeMeld(meld.id)}>
                          {text.remove}
                        </button>
                      </div>
                    </div>

                    <div className="ldg-grid-3" style={{ marginBottom: '0.75rem' }}>
                      <div className="ldg-field">
                        <label className="ldg-field__label">{text.meldType}</label>
                        <select
                          className="ldg-select"
                          value={meld.type}
                          onChange={(event) => updateMeldType(meld.id, Number(event.target.value) as ActionType)}
                        >
                          {MELD_TYPE_OPTIONS.map((option) => (
                            <option key={option.value} value={option.value}>
                              {getMeldLabelForLang(option.value, lang)}
                            </option>
                          ))}
                        </select>
                      </div>

                      <div className="ldg-field">
                        <label className="ldg-field__label">{text.calledDirection}</label>
                        <select
                          className="ldg-select"
                          value={meld.calledDirection}
                          onChange={(event) => updateMeldDirection(meld.id, Number(event.target.value) as MeldDirection)}
                          disabled={
                            meld.type === ActionType.ACTION_CHII ||
                            (meld.type === ActionType.ACTION_KAN &&
                              (meld.kongContext === 'hasBuddingClosedKong' || meld.kongContext === 'hasBloomingClosedKong'))
                          }
                        >
                          {MELD_DIRECTION_OPTIONS.map((option) => (
                            <option key={option.value} value={option.value}>
                              {getDirectionLabelForLang(option.value, lang)}
                            </option>
                          ))}
                        </select>
                      </div>

                      <div className="ldg-field">
                        <label className="ldg-field__label">{text.calledTile}</label>
                        <select
                          className="ldg-select"
                          value={meld.calledTileIndex}
                          onChange={(event) => updateMeldCalledTileIndex(meld.id, Number(event.target.value))}
                          disabled={meld.tiles.length === 0}
                        >
                          {meld.tiles.length === 0 ? (
                            <option value={0}>{text.addTilesFirst}</option>
                          ) : (
                            meld.tiles.map((tile: CalcTileDraft, tileIndex: number) => (
                              <option key={tile.id} value={tileIndex}>
                                {tileIndex + 1}: {formatTile(tile)}
                              </option>
                            ))
                          )}
                        </select>
                      </div>
                    </div>

                    <TileRow
                      tiles={meld.tiles}
                      emptyLabel={text.meldEmpty}
                      onTileClick={(tileId) => removeMeldTile(meld.id, tileId)}
                    />

                    {isActive && (
                      <div className="ldg-palette-drawer" style={{ marginTop: '0.75rem' }}>
                        <div className="ldg-palette-drawer__head">{text.activeMeldPalette}</div>
                        <PaletteGrid onTileClick={(tile) => addTileToMeld(meld.id, tile)} />
                      </div>
                    )}

                    {meld.type === ActionType.ACTION_KAN && (
                      <div className="ldg-field" style={{ marginTop: '0.75rem' }}>
                        <label className="ldg-field__label">{text.kanContext}</label>
                        <select
                          className="ldg-select"
                          value={meld.kongContext}
                          onChange={(event) => updateMeldKongContext(meld.id, event.target.value as CalcKongContextKey)}
                        >
                          <option value="">{text.noKanContext}</option>
                          {KONG_FLAG_OPTIONS.map((option) => (
                            <option key={`${meld.id}-${option.key}`} value={option.key}>
                              {getKongFlagLabelForLang(option.key, lang)}
                            </option>
                          ))}
                        </select>
                      </div>
                    )}

                    {meldError && <p className="ldg-note ldg-note--err" style={{ marginTop: '0.5rem' }}>{meldError}</p>}
                  </div>
                )
              })
            )}

            <div className="ldg-tools-row" style={{ marginTop: '0.85rem', justifyContent: 'flex-start' }}>
              {MELD_TYPE_OPTIONS.map((option) => (
                <button key={option.value} type="button" className="ldg-btn" onClick={() => addMeld(option.value)}>
                  + {getMeldLabelForLang(option.value, lang)}
                </button>
              ))}
            </div>
          </section>

          {/* Round context */}
          <section className="ldg-section">
            <div className="ldg-section-row">
              <h2 className="ldg-section-title">{text.roundContext}</h2>
            </div>

            <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap', marginBottom: '1rem' }}>
              <span className="ldg-section-title" style={{ fontSize: '0.85rem', color: 'var(--ink-3)' }}>
                {text.winType}
              </span>
              <div className="ldg-toggle">
                <button
                  type="button"
                  className={`ldg-toggle__btn${isTsumo ? ' is-active' : ''}`}
                  onClick={() => { setIsTsumo(true); clearServerState() }}
                >
                  {text.tsumo}
                </button>
                <button
                  type="button"
                  className={`ldg-toggle__btn${!isTsumo ? ' is-active' : ''}`}
                  onClick={() => { setIsTsumo(false); clearServerState() }}
                >
                  {text.ron}
                </button>
              </div>
            </div>

            <div className="ldg-grid-2">
              <div className="ldg-field">
                <label className="ldg-field__label">{text.seatWind}</label>
                <select
                  className="ldg-select"
                  value={seatWind}
                  onChange={(event) => { setSeatWind(Number(event.target.value)); clearServerState() }}
                >
                  {WIND_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {getWindLabelForLang(option.value, lang)}
                    </option>
                  ))}
                </select>
              </div>
              <div className="ldg-field">
                <label className="ldg-field__label">{text.prevailingWind}</label>
                <select
                  className="ldg-select"
                  value={prevailingWind}
                  onChange={(event) => { setPrevailingWind(Number(event.target.value)); clearServerState() }}
                >
                  {WIND_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {getWindLabelForLang(option.value, lang)}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="ldg-check-row" style={{ marginTop: '0.75rem' }}>
              <div className="ldg-check-row__label">{text.flowerKong}</div>
              <input
                type="checkbox"
                checked={hasBloomingFlowerKong}
                onChange={(event) => { setHasBloomingFlowerKong(event.target.checked); clearServerState() }}
                style={{ width: '1rem', height: '1rem', cursor: 'pointer', accentColor: 'var(--accent)' }}
              />
            </div>
          </section>

          {/* Flower melds */}
          <section className="ldg-section">
            <div className="ldg-section-row">
              <h2 className="ldg-section-title">{text.flowerMelds}</h2>
              <span className="ldg-section-meta">{flowerMelds.length > 0 ? flowerMelds.join(', ') : '—'}</span>
            </div>
            <div className="ldg-chips-row">
              {FLOWER_OPTIONS.map((flower) => {
                const selected = flowerMelds.includes(flower.value)
                return (
                  <button
                    key={flower.value}
                    type="button"
                    className={`ldg-chip${selected ? ' ldg-chip--active' : ''}`}
                    onClick={() => toggleFlower(flower.value)}
                  >
                    {flower.label}
                  </button>
                )
              })}
            </div>
          </section>

          {/* Actions row: validation + calculate */}
          <div className="ldg-actions-row">
            <div className="ldg-validation-area">
              {allErrors.length > 0 ? (
                <ul className="ldg-error-list">
                  {allErrors.map((err, i) => (
                    <li key={`${err}-${i}`}>{err}</li>
                  ))}
                </ul>
              ) : (
                <span className="ldg-note ldg-note--ok" style={{ marginTop: 0 }}>{text.noValidationErrors}</span>
              )}
            </div>
            <button
              type="button"
              className="ldg-btn ldg-btn--primary"
              onClick={handleCalculate}
              disabled={isSubmitting}
            >
              {isSubmitting ? text.calculating : text.calculatePoints}
            </button>
          </div>

          {/* Result */}
          <section className="ldg-result">
            <div className="ldg-result-row">
              <div className="ldg-result-label">{text.result}</div>
              <div className={`ldg-result-status${
                result
                  ? result.canWin ? ' ldg-result-status--ok' : ' ldg-result-status--err'
                  : ''
              }`}>
                {result
                  ? result.canWin ? text.validHand : text.invalidHand
                  : text.awaitingEvaluation}
              </div>
            </div>

            {result ? (
              <>
                <div className="ldg-big-stat">
                  <div className="ldg-big-stat__label">{text.totalScore}</div>
                  <div className="ldg-big-stat__value">{result.score}</div>
                </div>

                {result.entries.length > 0 ? (
                  <ul className="ldg-breakdown">
                    {result.entries.map((entry) => (
                      <li key={`${entry.patternName}-${entry.points}`}>
                        <span className="ldg-breakdown__name">{entry.patternName}</span>
                        <span className="ldg-breakdown__pts">+{entry.points}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="ldg-note">{text.noEntries}</p>
                )}
              </>
            ) : (
              <p className="ldg-note">{text.submitToSeeResult}</p>
            )}
          </section>

          {/* Normalized debug (collapsible) */}
          <div className="ldg-footnote">
            <button
              type="button"
              className="ldg-footnote__toggle"
              onClick={() => setShowDebug(v => !v)}
            >
              {showDebug ? '▴' : '▾'} {showDebug ? text.hideDebug : text.showDebug}
            </button>

            {showDebug && result && (
              <div style={{ marginTop: '1.25rem' }}>
                <div className="ldg-grid-2" style={{ gap: '0.6rem' }}>
                  <div className="ldg-debug">
                    <div className="ldg-debug__label">{text.closedHand}</div>
                    <div className="ldg-debug__value">{result.normalized.closedHand || text.none}</div>
                  </div>
                  <div className="ldg-debug">
                    <div className="ldg-debug__label">{text.winTile}</div>
                    <div className="ldg-debug__value">{result.normalized.winTile || text.none}</div>
                  </div>
                  <div className="ldg-debug">
                    <div className="ldg-debug__label">{text.wildTile}</div>
                    <div className="ldg-debug__value">{result.normalized.wildTile || text.none}</div>
                  </div>
                  <div className="ldg-debug">
                    <div className="ldg-debug__label">{text.context}</div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.4rem', marginTop: '0.2rem' }}>
                      <div className="ldg-kv">
                        <div className="ldg-kv__key">{text.winType}</div>
                        <div className="ldg-kv__val">{localizeDebugValue(result.normalized.winType, lang) || text.none}</div>
                      </div>
                      <div className="ldg-kv">
                        <div className="ldg-kv__key">{text.seatWind}</div>
                        <div className="ldg-kv__val">{localizeDebugValue(result.normalized.seatWind, lang) || text.none}</div>
                      </div>
                      <div className="ldg-kv">
                        <div className="ldg-kv__key">{text.prevailingWind}</div>
                        <div className="ldg-kv__val">{localizeDebugValue(result.normalized.prevailingWind, lang) || text.none}</div>
                      </div>
                      <div className="ldg-kv">
                        <div className="ldg-kv__key">{text.expectedClosedHandLength}</div>
                        <div className="ldg-kv__val">{result.normalized.expectedHandLen}</div>
                      </div>
                    </div>
                  </div>
                </div>

                {result.normalized.openMelds.length > 0 && (
                  <div className="ldg-debug" style={{ marginTop: '0.6rem' }}>
                    <div className="ldg-debug__label">{text.openMeldsTitle}</div>
                    {result.normalized.openMelds.map((meld, index) => (
                      <div key={`${meld.type}-${meld.tiles}-${index}`} style={{ marginTop: '0.5rem', fontSize: '0.85rem' }}>
                        <div style={{ fontFamily: 'var(--mono)', color: 'var(--ink-2)' }}>
                          {localizeDebugValue(meld.type, lang)}({meld.tiles})
                          {' · '}{text.calledTile} {meld.calledTile} #{meld.calledTileIndex + 1}
                          {' · '}{localizeDebugValue(meld.calledDirection, lang)}
                        </div>
                        {meld.kongFlags.length > 0 && (
                          <div className="ldg-chips-row" style={{ marginTop: '0.3rem' }}>
                            {meld.kongFlags.map((flag) => (
                              <span key={flag} className="ldg-chip">{localizeDebugValue(flag, lang)}</span>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                <div className="ldg-grid-2" style={{ gap: '0.6rem', marginTop: '0.6rem' }}>
                  <div className="ldg-debug">
                    <div className="ldg-debug__label">{text.flowerMelds}</div>
                    {result.normalized.flowerMelds.length === 0 ? (
                      <span className="ldg-debug__value">{text.none}</span>
                    ) : (
                      <div className="ldg-chips-row">
                        {result.normalized.flowerMelds.map((flower) => (
                          <span key={flower} className="ldg-chip">{flower}</span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="ldg-debug">
                    <div className="ldg-debug__label">{text.kanContext}</div>
                    {result.normalized.kongFlags.length === 0 ? (
                      <span className="ldg-debug__value">{text.none}</span>
                    ) : (
                      <div className="ldg-chips-row">
                        {result.normalized.kongFlags.map((flag) => (
                          <span key={flag} className="ldg-chip">{localizeDebugValue(flag, lang)}</span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            {showDebug && !result && (
              <p className="ldg-note" style={{ marginTop: '0.75rem' }}>{text.evaluateToCapture}</p>
            )}
          </div>

        </article>
      </div>
    </div>
  )
}
