import { useEffect, useState } from 'react'

import { getApiUrl } from '../config'
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
    title: 'Fenghua Calculator',
    subtitle: 'Compose a hand visually or by notation, set full scoring context, then evaluate against the backend rules engine.',
    closedHand: 'Closed hand',
    winTile: 'Win tile',
    wildTile: 'Wild tile',
    expectedCount: 'Expected count',
    openMelds: 'open meld(s)',
    apply: 'Apply',
    edit: 'Edit',
    tilePalette: 'Tile palette',
    closedHandPaletteHelp: 'Add tiles directly into the closed hand here.',
    winTilePaletteHelp: 'Pick the winning tile directly here.',
    wildTilePaletteHelp: 'Pick the round wild tile directly here.',
    noClosedHand: 'No tiles in the closed hand yet.',
    winTileHelp: 'Required for both tsumo and ron checks.',
    noWinTile: 'No win tile selected.',
    wildHelp: 'Exactly one tile type per round, or leave blank.',
    noWildTile: 'No wild tile selected.',
    openMeldsTitle: 'Open Melds',
    openMeldsHelp: 'Create chii, pon, or kan rows and compose them in-place.',
    activeMeldPalette: 'Meld palette',
    activeMeldPaletteHelp: 'The active meld row gets its own local palette so you can compose it without scrolling back to the top.',
    add: 'Add',
    noOpenMelds: 'No open melds yet.',
    openMeld: 'Open Meld',
    tiles: 'tiles',
    usePalette: 'Use palette',
    clear: 'Clear',
    remove: 'Remove',
    meldType: 'Meld type',
    calledDirection: 'Called direction',
    calledTile: 'Called tile',
    addTilesFirst: 'Add tiles first',
    meldEmpty: 'Use the tile palette or change meld type to start composing.',
    kanContext: 'Kan Context',
    kanContextHelp: 'Choose one kong context for this kan meld.',
    noKanContext: 'No extra context',
    roundContext: 'Round Context',
    winType: 'Win type',
    tsumo: 'Tsumo',
    ron: 'Ron',
    seatWind: 'Seat wind',
    prevailingWind: 'Prevailing wind',
    flowerMelds: 'Flower Melds',
    flowerHelp: 'Toggle the flowers you’ve revealed. Values 1-8 map directly into the calculator context.',
    validation: 'Validation',
    validationHelp: 'Client checks run before the calculator request is sent.',
    calculating: 'Calculating...',
    calculatePoints: 'Calculate Points',
    noValidationErrors: 'No client-side validation issues detected.',
    result: 'Result',
    resultHelp: 'Backend-evaluated hand score and breakdown.',
    validHand: 'Valid hand',
    invalidHand: 'Invalid hand',
    awaitingEvaluation: 'Awaiting evaluation',
    totalScore: 'Total score',
    breakdown: 'Breakdown',
    noEntries: 'No scoring entries were returned.',
    submitToSeeResult: 'Submit a calculator request to see the backend score output here.',
    normalizedSummary: 'Normalized Debug Summary',
    normalizedHelp: 'This reflects the server-normalized request after translation and validation.',
    context: 'Context',
    expectedClosedHandLength: 'Expected closed hand length',
    none: 'None',
    evaluateToCapture: 'Evaluate a hand to capture the normalized debug summary.',
  },
  zh: {
    language: 'English',
    title: '奉化麻将算分器',
    subtitle: '可用图形或牌谱输入组手牌，设置完整算分上下文，再交给后端规则引擎计算。',
    closedHand: '手牌',
    winTile: '和牌',
    wildTile: '搭牌',
    expectedCount: '应有张数',
    openMelds: '副露',
    apply: '应用',
    edit: '编辑',
    tilePalette: '牌库',
    closedHandPaletteHelp: '在这里直接把牌加入手牌。',
    winTilePaletteHelp: '在这里直接选择和牌。',
    wildTilePaletteHelp: '在这里直接选择本局搭牌。',
    noClosedHand: '当前还没有手牌。',
    winTileHelp: '自摸和点炮都需要设置和牌。',
    noWinTile: '尚未选择和牌。',
    wildHelp: '每局只允许一种搭牌，也可以留空。',
    noWildTile: '尚未选择搭牌。',
    openMeldsTitle: '副露编辑',
    openMeldsHelp: '创建吃、碰、杠行，并在每行内直接组副露。',
    activeMeldPalette: '副露牌库',
    activeMeldPaletteHelp: '当前正在编辑的副露会显示一个局部牌库，不用再滚回页面顶部选牌。',
    add: '新增',
    noOpenMelds: '当前还没有副露。',
    openMeld: '副露',
    tiles: '张',
    usePalette: '牌库加牌',
    clear: '清空',
    remove: '删除',
    meldType: '副露类型',
    calledDirection: '吃碰来源方向',
    calledTile: '被叫牌',
    addTilesFirst: '请先加入牌张',
    meldEmpty: '使用上方牌库，或先切换副露类型开始编辑。',
    kanContext: '杠牌上下文',
    kanContextHelp: '为这一组杠选择一个杠牌上下文。',
    noKanContext: '无额外上下文',
    roundContext: '牌局上下文',
    winType: '和牌方式',
    tsumo: '自摸',
    ron: '点炮',
    seatWind: '门风',
    prevailingWind: '圈风',
    flowerMelds: '花牌',
    flowerHelp: '点选已亮出的花牌。数值 1-8 会直接送入算分上下文。',
    validation: '输入校验',
    validationHelp: '发送请求前会先进行前端校验。',
    calculating: '计算中...',
    calculatePoints: '计算分数',
    noValidationErrors: '当前没有前端校验错误。',
    result: '结果',
    resultHelp: '由后端规则引擎返回的算分结果。',
    validHand: '可和牌',
    invalidHand: '不可和牌',
    awaitingEvaluation: '等待计算',
    totalScore: '总分',
    breakdown: '明细',
    noEntries: '当前没有返回算分条目。',
    submitToSeeResult: '提交一次计算请求后，这里会显示后端返回结果。',
    normalizedSummary: '标准化调试摘要',
    normalizedHelp: '这里显示服务端完成转换和校验后的请求内容。',
    context: '上下文',
    expectedClosedHandLength: '应有手牌张数',
    none: '无',
    evaluateToCapture: '进行一次计算后，这里会显示标准化调试摘要。',
  },
} as const

const KONG_FLAG_OPTIONS: Array<{ key: keyof CalcKongFlags; label: string }> = [
  { key: 'hasBuddingDirectKong', label: 'Budding Direct Kong' },
  { key: 'hasBloomingDirectKong', label: 'Blooming Direct Kong' },
  { key: 'hasBuddingClosedKong', label: 'Budding Closed Kong' },
  { key: 'hasBloomingClosedKong', label: 'Blooming Closed Kong' },
  { key: 'hasBuddingRiskyKong', label: 'Budding Risky Kong' },
  { key: 'hasBloomingRiskyKong', label: 'Blooming Risky Kong' },
  { key: 'hasBloomingFlowerKong', label: 'Blooming Flower Kong' },
]

const MELD_TYPE_OPTIONS = [
  { value: ActionType.ACTION_CHII, label: 'Chii' },
  { value: ActionType.ACTION_PON, label: 'Pon' },
  { value: ActionType.ACTION_KAN, label: 'Kan' },
]

const MELD_DIRECTION_OPTIONS = [
  { value: MeldDirection.MELD_DIRECTION_RIGHT, label: 'Right' },
  { value: MeldDirection.MELD_DIRECTION_ACROSS, label: 'Across' },
  { value: MeldDirection.MELD_DIRECTION_LEFT, label: 'Left' },
]

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
  const sizeStyle = size === 'palette'
    ? {
        width: 'clamp(2.9rem, 4.6vw, 3.6rem)',
        height: 'clamp(4.2rem, 6.5vw, 5.2rem)',
        minWidth: '46px',
        minHeight: '66px',
      }
    : undefined

  return (
    <button
      type="button"
      onClick={onClick}
      className={`mahjong-tile ${size === 'small' ? 'small' : ''} rounded-md transition ${selected ? 'ring-2 ring-amber-400 ring-offset-2 ring-offset-slate-950' : ''} ${dimmed ? 'opacity-50' : ''}`}
      style={{
        padding: 0,
        border: 'none',
        backgroundColor: 'transparent',
        boxShadow: selected ? '0 0 14px rgba(251,191,36,0.7)' : '1px 1px 3px rgba(0,0,0,0.45)',
        position: 'relative',
        cursor: onClick ? 'pointer' : 'default',
        ...sizeStyle,
      }}
      title={getTileName(tile)}
    >
      <img
        src="/Regular_shortnames/Front.svg"
        alt=""
        draggable="false"
        style={{ width: '100%', height: '100%', display: 'block', borderRadius: '4px', position: 'absolute', top: 0, left: 0, zIndex: 1 }}
      />
      <img
        src={`/Regular_shortnames/${svgName}`}
        alt={getTileName(tile)}
        draggable="false"
        style={{ width: '85%', height: '85%', display: 'block', position: 'absolute', top: '7.5%', left: '7.5%', zIndex: 2 }}
      />
    </button>
  )
}

function TileRow({
  tiles,
  emptyLabel,
  onTileClick,
}: {
  tiles: CalcTileDraft[]
  emptyLabel: string
  onTileClick: (tileId: string) => void
}) {
  if (tiles.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-slate-700 bg-slate-950/60 px-4 py-5 text-sm text-slate-400">
        {emptyLabel}
      </div>
    )
  }

  return (
    <div className="flex flex-wrap gap-2 rounded-xl border border-slate-700 bg-slate-950/60 p-3">
      {tiles.map((tile) => (
        <CalcTile key={tile.id} tile={tile} onClick={() => onTileClick(tile.id)} />
      ))}
    </div>
  )
}

function PaletteGrid({
  onTileClick,
  selectedTile = null,
  dimSelected = false,
}: {
  onTileClick: (tile: CalcTileValue) => void
  selectedTile?: CalcTileDraft | null
  dimSelected?: boolean
}) {
  return (
    <div className="flex flex-wrap gap-3 md:gap-4">
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

function parseErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Unknown calculator error.'
}

function getMeldLabelForLang(type: ActionType, lang: Lang): string {
  const label = getMeldLabel(type)
  if (lang === 'en') {
    return label
  }

  switch (label) {
    case 'Chii':
      return '吃'
    case 'Pon':
      return '碰'
    case 'Kan':
      return '杠'
    default:
      return label
  }
}

function getDirectionLabelForLang(direction: MeldDirection, lang: Lang): string {
  const label = getDirectionLabel(direction)
  if (lang === 'en') {
    return label
  }

  switch (label) {
    case 'Right':
      return '右家'
    case 'Across':
      return '对家'
    case 'Left':
      return '左家'
    default:
      return label
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
  if (lang === 'en' || !value) {
    return value
  }

  const translations: Record<string, string> = {
    East: '东',
    South: '南',
    West: '西',
    North: '北',
    tsumo: '自摸',
    ron: '点炮',
    chii: '吃',
    pon: '碰',
    kan: '杠',
    right: '右家',
    across: '对家',
    left: '左家',
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

export default function Calc() {
  const [lang, setLang] = useState<Lang>('en')
  const [closedHand, setClosedHand] = useState<CalcTileDraft[]>([])
  const [winTile, setWinTile] = useState<CalcTileDraft | null>(null)
  const [wildTile, setWildTile] = useState<CalcTileDraft | null>(null)
  const [openMelds, setOpenMelds] = useState<CalcMeldDraft[]>([])
  const [flowerMelds, setFlowerMelds] = useState<number[]>([])
  const [isTsumo, setIsTsumo] = useState(true)
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

  useEffect(() => {
    setClosedHandInput(formatTehai(closedHand))
  }, [closedHand])

  useEffect(() => {
    setWinTileInput(formatTile(winTile))
  }, [winTile])

  useEffect(() => {
    setWildTileInput(formatTile(wildTile))
  }, [wildTile])

  const validationErrors = validateCalculatorState({
    closedHand,
    winTile,
    wildTile,
    openMelds,
    flowerMelds,
    seatWind,
    prevailingWind,
  })

  const clearServerState = () => {
    setResult(null)
    setServerErrors([])
  }

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
        if (meld.id !== meldId) {
          return meld
        }
        if (meld.tiles.length >= meldRequiredTileCount(meld.type)) {
          return meld
        }
        return {
          ...meld,
          tiles: [...meld.tiles, createTileDraft(tile)],
        }
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
        if (meld.id !== meldId) {
          return meld
        }

        const nextTiles = meld.tiles.filter((tile: CalcTileDraft) => tile.id !== tileId)
        const nextCalledTileIndex = nextTiles.length === 0 ? 0 : Math.min(meld.calledTileIndex, nextTiles.length - 1)
        return {
          ...meld,
          tiles: nextTiles,
          calledTileIndex: nextCalledTileIndex,
        }
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
        if (meld.id !== meldId) {
          return meld
        }
        const requiredCount = meldRequiredTileCount(type)
        const nextTiles = meld.tiles.slice(0, requiredCount)
        const nextCalledTileIndex = nextTiles.length === 0 ? 0 : Math.min(meld.calledTileIndex, nextTiles.length - 1)
        return {
          ...meld,
          type,
          tiles: nextTiles,
          calledTileIndex: nextCalledTileIndex,
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
          ? {
              ...meld,
              tiles: [],
              calledTileIndex: 0,
              kongContext: meld.type === ActionType.ACTION_KAN ? '' : meld.kongContext,
            }
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
        if (meld.id !== meldId || meld.type !== ActionType.ACTION_KAN) {
          return meld
        }

        return {
          ...meld,
          kongContext: value,
        }
      }),
    )
    clearServerState()
  }

  const handleCalculate = async () => {
    const nextClosedHand = applyClosedHandInput()
    const nextWinTile = applyWinTileInput()
    const nextWildTile = applyWildTileInput()

    if (nextClosedHand === null || nextWinTile === undefined || nextWildTile === undefined) {
      return
    }

    const effectiveClosedHand = nextClosedHand
    const effectiveWinTile = nextWinTile
    const effectiveWildTile = nextWildTile

    const nextValidationErrors = validateCalculatorState({
      closedHand: effectiveClosedHand,
      winTile: effectiveWinTile ?? null,
      wildTile: effectiveWildTile ?? null,
      openMelds,
      flowerMelds,
      seatWind,
      prevailingWind,
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
      openMelds,
      flowerMelds,
      seatWind,
      prevailingWind,
      isTsumo,
    })

    setIsSubmitting(true)
    setServerErrors([])

    try {
      const response = await fetch(getApiUrl('/api/v1/calc'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })

      if (!response.ok) {
        const errorPayload = normalizeCalcErrorResponse(await response.json())
        setResult(null)
        setServerErrors(errorPayload.errors ?? ['Calculator request failed.'])
        return
      }

      const successPayload = normalizeCalcSuccessResponse(await response.json())
      setResult(successPayload)
    } catch (error) {
      setResult(null)
      setServerErrors([parseErrorMessage(error)])
    } finally {
      setIsSubmitting(false)
    }
  }

  const highlightedMeldId = activeMeldId
  const combinedErrors = [...inputErrors.closedHand, ...inputErrors.winTile, ...inputErrors.wildTile, ...serverErrors]
  const expectedHandLength = expectedClosedHandSize(openMelds.length)
  const text = UI_TEXT[lang]

  return (
    <div className="w-full bg-slate-950 text-slate-100">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-4 py-6 lg:px-8">
        <section className="rounded-3xl border border-slate-800 bg-gradient-to-br from-slate-900 via-slate-900 to-slate-950 p-6 shadow-2xl">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <h1 className="text-3xl font-black tracking-tight text-amber-300">{text.title}</h1>
              <p className="mt-2 max-w-3xl text-sm text-slate-300">
                {text.subtitle}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => setLang((current) => (current === 'en' ? 'zh' : 'en'))}
                className="rounded-full border border-amber-400/40 bg-slate-900 px-4 py-2 text-sm font-semibold text-amber-200 transition hover:bg-slate-800"
              >
                {text.language}
              </button>
            </div>
          </div>
        </section>

        <section className="grid gap-6 xl:grid-cols-[1.4fr_1fr]">
          <div className="flex flex-col gap-6">
            <div className="rounded-3xl border border-slate-800 bg-slate-900/70 p-5 shadow-xl">
              <div className="mb-4 flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-xl font-bold text-slate-100">{text.closedHand}</h2>
                  <p className="text-sm text-slate-400">
                    {text.expectedCount}: {expectedHandLength} {text.tiles} / {openMelds.length} {text.openMelds}
                  </p>
                </div>
                {collapsedSections.closedHand && (
                  <button
                    type="button"
                    onClick={() => setCollapsedSections((current) => ({ ...current, closedHand: false }))}
                    className="rounded-full bg-slate-800 px-3 py-2 text-sm font-semibold text-slate-100 transition hover:bg-slate-700"
                  >
                    {text.edit}
                  </button>
                )}
              </div>
              {!collapsedSections.closedHand && (
                <div className="mb-4 flex flex-col gap-3 lg:flex-row">
                  <input
                    value={closedHandInput}
                    onChange={(event) => setClosedHandInput(event.target.value)}
                    placeholder="1m2m3m 4p5p6p 7s8s9s 3z"
                    className="w-full rounded-2xl border border-slate-700 bg-slate-950 px-4 py-3 font-mono text-sm text-slate-100 outline-none transition focus:border-amber-400"
                  />
                  <button type="button" onClick={applyClosedHandInput} className="rounded-2xl bg-slate-800 px-4 py-3 text-sm font-semibold text-slate-100 transition hover:bg-slate-700">
                    {text.apply}
                  </button>
                </div>
              )}
              <TileRow tiles={closedHand} emptyLabel={text.noClosedHand} onTileClick={removeClosedHandTile} />
              {!collapsedSections.closedHand && (
                <div className="mt-4 rounded-2xl border border-slate-700 bg-slate-950/60 p-4">
                  <div className="mb-3">
                    <h3 className="text-sm font-semibold uppercase tracking-wide text-amber-200">{text.tilePalette}</h3>
                    <p className="text-xs text-slate-400">{text.closedHandPaletteHelp}</p>
                  </div>
                  <PaletteGrid onTileClick={addTileToClosedHand} />
                </div>
              )}
            </div>

            <div className="grid gap-6 lg:grid-cols-2">
              <div className="rounded-3xl border border-slate-800 bg-slate-900/70 p-5 shadow-xl">
                <div className="mb-4 flex items-start justify-between gap-3">
                  <div>
                    <h2 className="text-xl font-bold text-slate-100">{text.winTile}</h2>
                    <p className="text-sm text-slate-400">{text.winTileHelp}</p>
                  </div>
                  {collapsedSections.winTile && (
                    <div className="flex items-center gap-3">
                      {winTile ? (
                        <CalcTile tile={winTile} onClick={() => { setWinTile(null); clearServerState() }} size="small" />
                      ) : (
                        <span className="text-sm text-slate-400">{text.noWinTile}</span>
                      )}
                      <button
                        type="button"
                        onClick={() => setCollapsedSections((current) => ({ ...current, winTile: false }))}
                        className="rounded-full bg-slate-800 px-3 py-2 text-sm font-semibold text-slate-100 transition hover:bg-slate-700"
                      >
                        {text.edit}
                      </button>
                    </div>
                  )}
                </div>
                {!collapsedSections.winTile && (
                  <div className="mb-4 flex gap-3">
                    <input
                      value={winTileInput}
                      onChange={(event) => setWinTileInput(event.target.value)}
                      placeholder="3z"
                      className="w-full rounded-2xl border border-slate-700 bg-slate-950 px-4 py-3 font-mono text-sm text-slate-100 outline-none transition focus:border-amber-400"
                    />
                    <button type="button" onClick={applyWinTileInput} className="rounded-2xl bg-slate-800 px-4 py-3 text-sm font-semibold text-slate-100 transition hover:bg-slate-700">
                      {text.apply}
                    </button>
                  </div>
                )}
                {!collapsedSections.winTile && (
                  <div className="flex min-h-24 items-center justify-center rounded-xl border border-slate-700 bg-slate-950/60 p-4">
                    {winTile ? (
                      <CalcTile tile={winTile} onClick={() => { setWinTile(null); clearServerState() }} />
                    ) : (
                      <span className="text-sm text-slate-400">{text.noWinTile}</span>
                    )}
                  </div>
                )}
                {!collapsedSections.winTile && (
                  <div className="mt-4 rounded-2xl border border-slate-700 bg-slate-950/60 p-4">
                    <div className="mb-3">
                      <h3 className="text-sm font-semibold uppercase tracking-wide text-amber-200">{text.tilePalette}</h3>
                      <p className="text-xs text-slate-400">{text.winTilePaletteHelp}</p>
                    </div>
                    <PaletteGrid
                      onTileClick={(tile) => {
                        setWinTile(createTileDraft(tile))
                        clearServerState()
                      }}
                      selectedTile={winTile}
                    />
                  </div>
                )}
              </div>

              <div className="rounded-3xl border border-slate-800 bg-slate-900/70 p-5 shadow-xl">
                <div className="mb-4 flex items-start justify-between gap-3">
                  <div>
                    <h2 className="text-xl font-bold text-slate-100">{text.wildTile}</h2>
                    <p className="text-sm text-slate-400">{text.wildHelp}</p>
                  </div>
                  {collapsedSections.wildTile && (
                    <div className="flex items-center gap-3">
                      {wildTile ? (
                        <CalcTile tile={wildTile} onClick={() => { setWildTile(null); clearServerState() }} size="small" selected />
                      ) : (
                        <span className="text-sm text-slate-400">{text.noWildTile}</span>
                      )}
                      <button
                        type="button"
                        onClick={() => setCollapsedSections((current) => ({ ...current, wildTile: false }))}
                        className="rounded-full bg-slate-800 px-3 py-2 text-sm font-semibold text-slate-100 transition hover:bg-slate-700"
                      >
                        {text.edit}
                      </button>
                    </div>
                  )}
                </div>
                {!collapsedSections.wildTile && (
                  <div className="mb-4 flex gap-3">
                    <input
                      value={wildTileInput}
                      onChange={(event) => setWildTileInput(event.target.value)}
                      placeholder="9s"
                      className="w-full rounded-2xl border border-slate-700 bg-slate-950 px-4 py-3 font-mono text-sm text-slate-100 outline-none transition focus:border-amber-400"
                    />
                    <button type="button" onClick={applyWildTileInput} className="rounded-2xl bg-slate-800 px-4 py-3 text-sm font-semibold text-slate-100 transition hover:bg-slate-700">
                      {text.apply}
                    </button>
                  </div>
                )}
                {!collapsedSections.wildTile && (
                  <div className="flex min-h-24 items-center justify-center rounded-xl border border-slate-700 bg-slate-950/60 p-4">
                    {wildTile ? (
                      <CalcTile tile={wildTile} onClick={() => { setWildTile(null); clearServerState() }} selected />
                    ) : (
                      <span className="text-sm text-slate-400">{text.noWildTile}</span>
                    )}
                  </div>
                )}
                {!collapsedSections.wildTile && (
                  <div className="mt-4 rounded-2xl border border-slate-700 bg-slate-950/60 p-4">
                    <div className="mb-3">
                      <h3 className="text-sm font-semibold uppercase tracking-wide text-amber-200">{text.tilePalette}</h3>
                      <p className="text-xs text-slate-400">{text.wildTilePaletteHelp}</p>
                    </div>
                    <PaletteGrid
                      onTileClick={(tile) => {
                        setWildTile(createTileDraft(tile))
                        clearServerState()
                      }}
                      selectedTile={wildTile}
                      dimSelected
                    />
                  </div>
                )}
              </div>
            </div>

            <div className="rounded-3xl border border-slate-800 bg-slate-900/70 p-5 shadow-xl">
              <div className="mb-4">
                <div>
                  <h2 className="text-xl font-bold text-slate-100">{text.openMeldsTitle}</h2>
                  <p className="text-sm text-slate-400">{text.openMeldsHelp}</p>
                </div>
              </div>

              <div className="flex flex-col gap-4">
                {openMelds.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-slate-700 bg-slate-950/60 px-4 py-5 text-sm text-slate-400">
                    {text.noOpenMelds}
                  </div>
                ) : (
                  openMelds.map((meld, index) => {
                    const meldError = validateMeldShape(meld)
                    const isActiveTarget = highlightedMeldId === meld.id
                    return (
                      <div key={meld.id} className={`rounded-2xl border p-4 ${isActiveTarget ? 'border-amber-400 bg-amber-400/5' : 'border-slate-700 bg-slate-950/60'}`}>
                        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                          <div>
                            <h3 className="text-lg font-bold text-slate-100">{text.openMeld} {index + 1}</h3>
                            <p className="text-sm text-slate-400">
                              {meld.tiles.length}/{meldRequiredTileCount(meld.type)} {text.tiles} • {getDirectionLabelForLang(meld.calledDirection, lang)}
                            </p>
                          </div>
                          <div className="flex flex-wrap gap-2">
                            <button type="button" onClick={() => setActiveMeldId(meld.id)} className={`rounded-full px-3 py-2 text-sm font-semibold ${isActiveTarget ? 'bg-amber-400 text-slate-950' : 'bg-slate-800 text-slate-100 hover:bg-slate-700'}`}>
                              {text.usePalette}
                            </button>
                            <button type="button" onClick={() => clearMeld(meld.id)} className="rounded-full bg-slate-800 px-3 py-2 text-sm font-semibold text-slate-100 transition hover:bg-slate-700">
                              {text.clear}
                            </button>
                            <button type="button" onClick={() => removeMeld(meld.id)} className="rounded-full bg-red-500/20 px-3 py-2 text-sm font-semibold text-red-200 transition hover:bg-red-500/30">
                              {text.remove}
                            </button>
                          </div>
                        </div>

                        <div className="mb-4 grid gap-3 md:grid-cols-3">
                          <label className="flex flex-col gap-2 text-sm text-slate-300">
                            {text.meldType}
                            <select
                              value={meld.type}
                              onChange={(event) => updateMeldType(meld.id, Number(event.target.value) as ActionType)}
                              className="rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100 outline-none focus:border-amber-400"
                            >
                              {MELD_TYPE_OPTIONS.map((option) => (
                                <option key={option.value} value={option.value}>
                                  {getMeldLabelForLang(option.value, lang)}
                                </option>
                              ))}
                            </select>
                          </label>

                          <label className="flex flex-col gap-2 text-sm text-slate-300">
                            {text.calledDirection}
                            <select
                              value={meld.calledDirection}
                              onChange={(event) => updateMeldDirection(meld.id, Number(event.target.value) as MeldDirection)}
                              className="rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100 outline-none focus:border-amber-400"
                              disabled={meld.type === ActionType.ACTION_CHII}
                            >
                              {MELD_DIRECTION_OPTIONS.map((option) => (
                                <option key={option.value} value={option.value}>
                                  {getDirectionLabelForLang(option.value, lang)}
                                </option>
                              ))}
                            </select>
                          </label>

                          <label className="flex flex-col gap-2 text-sm text-slate-300">
                            {text.calledTile}
                            <select
                              value={meld.calledTileIndex}
                              onChange={(event) => updateMeldCalledTileIndex(meld.id, Number(event.target.value))}
                              className="rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100 outline-none focus:border-amber-400"
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
                          </label>
                        </div>

                        <TileRow tiles={meld.tiles} emptyLabel={text.meldEmpty} onTileClick={(tileId) => removeMeldTile(meld.id, tileId)} />

                        {isActiveTarget && (
                          <div className="mt-4 rounded-2xl border border-amber-400/30 bg-slate-900/80 p-4">
                            <div className="mb-3">
                              <h4 className="text-sm font-semibold uppercase tracking-wide text-amber-200">{text.activeMeldPalette}</h4>
                              <p className="text-xs text-slate-400">{text.activeMeldPaletteHelp}</p>
                            </div>
                            <PaletteGrid onTileClick={(tile) => addTileToMeld(meld.id, tile)} />
                          </div>
                        )}

                        {meld.type === ActionType.ACTION_KAN && (
                          <div className="mt-4 grid gap-2">
                            <label className="flex flex-col gap-2 text-sm text-slate-300">
                              {text.kanContext}
                              <select
                                value={meld.kongContext}
                                onChange={(event) => updateMeldKongContext(meld.id, event.target.value as CalcKongContextKey)}
                                className="rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100 outline-none focus:border-amber-400"
                              >
                                <option value="">{text.noKanContext}</option>
                                {KONG_FLAG_OPTIONS.map((option) => (
                                  <option key={`${meld.id}-${option.key}`} value={option.key}>
                                    {getKongFlagLabelForLang(option.key, lang)}
                                  </option>
                                ))}
                              </select>
                            </label>
                            <p className="text-xs text-slate-400">{text.kanContextHelp}</p>
                          </div>
                        )}

                        {meldError && <p className="mt-3 text-sm text-rose-300">{meldError}</p>}
                      </div>
                    )
                  })
                )}
              </div>

              <div className="mt-4 flex flex-wrap gap-2">
                {MELD_TYPE_OPTIONS.map((option) => (
                  <button key={option.value} type="button" onClick={() => addMeld(option.value)} className="rounded-full bg-slate-800 px-3 py-2 text-sm font-semibold text-slate-100 transition hover:bg-slate-700">
                    {text.add} {getMeldLabelForLang(option.value, lang)}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="flex flex-col gap-6">
            <div className="rounded-3xl border border-slate-800 bg-slate-900/70 p-5 shadow-xl">
              <h2 className="mb-4 text-xl font-bold text-slate-100">{text.roundContext}</h2>
              <div className="grid gap-4">
                <label className="flex items-center justify-between rounded-2xl border border-slate-700 bg-slate-950/60 px-4 py-3 text-sm text-slate-200">
                  <span>{text.winType}</span>
                  <button type="button" onClick={() => { setIsTsumo((current) => !current); clearServerState() }} className={`rounded-full px-4 py-2 font-semibold ${isTsumo ? 'bg-emerald-400 text-slate-950' : 'bg-slate-800 text-slate-100'}`}>
                    {isTsumo ? text.tsumo : text.ron}
                  </button>
                </label>

                <div className="grid gap-4 sm:grid-cols-2">
                  <label className="flex flex-col gap-2 text-sm text-slate-300">
                    {text.seatWind}
                    <select
                      value={seatWind}
                      onChange={(event) => { setSeatWind(Number(event.target.value)); clearServerState() }}
                      className="rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-amber-400"
                    >
                      {WIND_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {getWindLabelForLang(option.value, lang)}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label className="flex flex-col gap-2 text-sm text-slate-300">
                    {text.prevailingWind}
                    <select
                      value={prevailingWind}
                      onChange={(event) => { setPrevailingWind(Number(event.target.value)); clearServerState() }}
                      className="rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-amber-400"
                    >
                      {WIND_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {getWindLabelForLang(option.value, lang)}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              </div>
            </div>

            <div className="rounded-3xl border border-slate-800 bg-slate-900/70 p-5 shadow-xl">
              <div className="mb-4">
                <h2 className="text-xl font-bold text-slate-100">{text.flowerMelds}</h2>
                <p className="text-sm text-slate-400">{text.flowerHelp}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                {FLOWER_OPTIONS.map((flower) => {
                  const selected = flowerMelds.includes(flower.value)
                  return (
                    <button
                      key={flower.value}
                      type="button"
                      onClick={() => toggleFlower(flower.value)}
                      className={`rounded-full px-3 py-2 text-sm font-semibold transition ${selected ? 'bg-emerald-400 text-slate-950' : 'bg-slate-800 text-slate-100 hover:bg-slate-700'}`}
                    >
                      {flower.label}
                    </button>
                  )
                })}
              </div>
            </div>

            <div className="rounded-3xl border border-slate-800 bg-slate-900/70 p-5 shadow-xl">
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-xl font-bold text-slate-100">{text.validation}</h2>
                  <p className="text-sm text-slate-400">{text.validationHelp}</p>
                </div>
                <button
                  type="button"
                  onClick={handleCalculate}
                  disabled={isSubmitting}
                  className="rounded-full bg-amber-400 px-5 py-3 text-sm font-black uppercase tracking-wide text-slate-950 transition hover:bg-amber-300 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-300"
                >
                  {isSubmitting ? text.calculating : text.calculatePoints}
                </button>
              </div>

              <div className="rounded-2xl border border-slate-700 bg-slate-950/60 p-4 text-sm">
                {combinedErrors.length > 0 || validationErrors.length > 0 ? (
                  <ul className="space-y-2 text-rose-200">
                    {[...combinedErrors, ...validationErrors].map((error, index) => (
                      <li key={`${error}-${index}`}>{error}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-emerald-300">{text.noValidationErrors}</p>
                )}
              </div>
            </div>
          </div>
        </section>

        <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
          <div className={`rounded-3xl border p-5 shadow-xl ${result?.canWin ? 'border-emerald-400/60 bg-emerald-500/10' : 'border-slate-800 bg-slate-900/70'}`}>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-xl font-bold text-slate-100">{text.result}</h2>
                <p className="text-sm text-slate-400">{text.resultHelp}</p>
              </div>
              <div className={`rounded-full px-4 py-2 text-sm font-black uppercase tracking-wide ${result?.canWin ? 'bg-emerald-400 text-slate-950' : 'bg-slate-800 text-slate-100'}`}>
                {result ? (result.canWin ? text.validHand : text.invalidHand) : text.awaitingEvaluation}
              </div>
            </div>

            {result ? (
              <div className="space-y-4">
                <div className="rounded-2xl border border-slate-700 bg-slate-950/60 p-4">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-slate-400">{text.totalScore}</span>
                    <span className="text-3xl font-black text-amber-300">{result.score}</span>
                  </div>
                </div>

                <div className="rounded-2xl border border-slate-700 bg-slate-950/60 p-4">
                  <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">{text.breakdown}</h3>
                  <div className="space-y-2">
                    {result.entries.length === 0 ? (
                      <p className="text-sm text-slate-400">{text.noEntries}</p>
                    ) : (
                      result.entries.map((entry) => (
                        <div key={`${entry.patternName}-${entry.points}`} className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-900 px-3 py-2">
                          <span className="text-sm text-slate-200">{entry.patternName}</span>
                          <span className="text-sm font-bold text-emerald-300">+{entry.points}</span>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>
            ) : (
              <div className="rounded-2xl border border-dashed border-slate-700 bg-slate-950/60 px-4 py-8 text-center text-sm text-slate-400">
                {text.submitToSeeResult}
              </div>
            )}
          </div>

          <div className="rounded-3xl border border-slate-800 bg-slate-900/70 p-5 shadow-xl">
            <div className="mb-4">
              <h2 className="text-xl font-bold text-slate-100">{text.normalizedSummary}</h2>
              <p className="text-sm text-slate-400">{text.normalizedHelp}</p>
            </div>

            {result ? (
              <div className="space-y-4 text-sm">
                <div className="rounded-2xl border border-slate-700 bg-slate-950/60 p-4 font-mono text-slate-200">
                  <div className="mb-2 text-xs uppercase tracking-wide text-slate-500">{text.closedHand}</div>
                  <div>{result.normalized.closedHand || text.none}</div>
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                  <div className="rounded-2xl border border-slate-700 bg-slate-950/60 p-4 font-mono text-slate-200">
                    <div className="mb-2 text-xs uppercase tracking-wide text-slate-500">{text.winTile}</div>
                    <div>{result.normalized.winTile || text.none}</div>
                  </div>
                  <div className="rounded-2xl border border-slate-700 bg-slate-950/60 p-4 font-mono text-slate-200">
                    <div className="mb-2 text-xs uppercase tracking-wide text-slate-500">{text.wildTile}</div>
                    <div>{result.normalized.wildTile || text.none}</div>
                  </div>
                </div>

                <div className="rounded-2xl border border-slate-700 bg-slate-950/60 p-4">
                  <div className="mb-3 text-xs uppercase tracking-wide text-slate-500">{text.context}</div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div>
                      <div className="text-slate-400">{text.winType}</div>
                      <div className="font-semibold text-slate-100">{localizeDebugValue(result.normalized.winType, lang) || text.none}</div>
                    </div>
                    <div>
                      <div className="text-slate-400">{text.seatWind}</div>
                      <div className="font-semibold text-slate-100">{localizeDebugValue(result.normalized.seatWind, lang) || text.none}</div>
                    </div>
                    <div>
                      <div className="text-slate-400">{text.prevailingWind}</div>
                      <div className="font-semibold text-slate-100">{localizeDebugValue(result.normalized.prevailingWind, lang) || text.none}</div>
                    </div>
                    <div>
                      <div className="text-slate-400">{text.expectedClosedHandLength}</div>
                      <div className="font-semibold text-slate-100">{result.normalized.expectedHandLen}</div>
                    </div>
                  </div>
                </div>

                <div className="rounded-2xl border border-slate-700 bg-slate-950/60 p-4">
                  <div className="mb-3 text-xs uppercase tracking-wide text-slate-500">{text.openMeldsTitle}</div>
                  {result.normalized.openMelds.length === 0 ? (
                    <p className="text-slate-400">{text.none}</p>
                  ) : (
                    <div className="space-y-3">
                      {result.normalized.openMelds.map((meld, index) => (
                        <div key={`${meld.type}-${meld.tiles}-${index}`} className="rounded-xl border border-slate-800 bg-slate-900 px-3 py-3">
                          <div className="font-mono text-slate-100">{localizeDebugValue(meld.type, lang)}({meld.tiles})</div>
                          <div className="mt-1 text-xs text-slate-400">
                            {text.calledTile} {meld.calledTile} • #{meld.calledTileIndex + 1} • {localizeDebugValue(meld.calledDirection, lang)}
                          </div>
                          {meld.kongFlags.length > 0 && (
                            <div className="mt-2 flex flex-wrap gap-2">
                              {meld.kongFlags.map((flag) => (
                                <span key={flag} className="rounded-full bg-slate-800 px-3 py-1 text-xs text-slate-200">
                                  {localizeDebugValue(flag, lang)}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                  <div className="rounded-2xl border border-slate-700 bg-slate-950/60 p-4">
                    <div className="mb-3 text-xs uppercase tracking-wide text-slate-500">{text.flowerMelds}</div>
                    {result.normalized.flowerMelds.length === 0 ? (
                      <p className="text-slate-400">{text.none}</p>
                    ) : (
                      <div className="flex flex-wrap gap-2">
                        {result.normalized.flowerMelds.map((flower) => (
                          <span key={flower} className="rounded-full bg-slate-800 px-3 py-1 text-xs text-slate-200">
                            {flower}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="rounded-2xl border border-slate-700 bg-slate-950/60 p-4">
                    <div className="mb-3 text-xs uppercase tracking-wide text-slate-500">{text.kanContext}</div>
                    {result.normalized.kongFlags.length === 0 ? (
                      <p className="text-slate-400">{text.none}</p>
                    ) : (
                      <div className="flex flex-wrap gap-2">
                        {result.normalized.kongFlags.map((flag) => (
                          <span key={flag} className="rounded-full bg-slate-800 px-3 py-1 text-xs text-slate-200">
                            {localizeDebugValue(flag, lang)}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ) : (
              <div className="rounded-2xl border border-dashed border-slate-700 bg-slate-950/60 px-4 py-8 text-center text-sm text-slate-400">
                {text.evaluateToCapture}
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  )
}
