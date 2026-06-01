import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import PageShell from '../components/PageShell'
import { getApiUrl } from '../config'
import { getTileName, getTileSvgName } from '../utils/tileUtils'
import {
  countTiles,
  createDraft,
  decodeUrlState,
  DiscardOption,
  encodeUrlState,
  formatHand,
  formatTile,
  parseHand,
  remainingCount,
  sameTile,
  ShantenResult,
  sortHand,
  TileDraft,
  TILE_LIBRARY,
  TileValue,
  tileKey,
} from './shantenHelpers'

type Lang = 'en' | 'zh'

const TEXT = {
  en: {
    language: '中文',
    title: 'Shanten Calculator',
    subtitle: 'Build a hand (13 or 14 tiles). For 13 tiles, a random tile is drawn. Then discard analysis shows the best options.',
    closedHand: 'Closed Hand',
    tiles: 'tiles',
    openMelds: 'open melds',
    apply: 'Apply',
    tilePalette: 'Tile palette',
    paletteHelp: 'Click to add. Click tiles in hand to remove.',
    noTiles: 'Click tiles below to build your hand.',
    wildTile: 'Wild Tile (搭)',
    wildHelp: 'The round\'s wild tile type, if any.',
    noWild: 'None set',
    openMeldsLabel: 'Open Melds',
    openMeldsHelp: 'Number of open melds (chii/pon/kan).',
    result: 'Result',
    complete: 'Complete',
    tenpai: 'Tenpai',
    shantenAway: '-shanten',
    usefulTiles: 'Useful Tiles',
    usefulHelp: 'Draws that reduce shanten by 1.',
    noUseful: 'No useful tiles.',
    totalRemaining: 'tiles remaining',
    clear: 'Clear',
    sort: 'Sort',
    redraw: 'Redraw',
    drawnTileLabel: 'Drawn Tile',
    waiting13: 'Add tiles to build a hand.',
    error: 'Error',
    discard: 'Discard',
    draw: 'Draw',
    discardAnalysis: 'Discard Analysis',
    discardHelp: 'For each discard, shows which draws improve the hand.',
    count: 'count',
    edit: 'Edit',
    expected: 'Expected',
  },
  zh: {
    language: 'EN',
    title: '向听计算器',
    subtitle: '构建手牌（13或14张）。13张时随机摸牌，然后进行打牌分析。',
    closedHand: '手牌',
    tiles: '张',
    openMelds: '副露',
    apply: '确认',
    tilePalette: '选牌',
    paletteHelp: '点击添加。点击手牌中的牌可移除。',
    noTiles: '点击下方的牌来构建手牌。',
    wildTile: '搭牌（百搭）',
    wildHelp: '本轮的百搭牌种类。',
    noWild: '未设置',
    openMeldsLabel: '副露数',
    openMeldsHelp: '已有副露数量（吃/碰/杠）。',
    result: '结果',
    complete: '和了',
    tenpai: '听牌',
    shantenAway: '向听',
    usefulTiles: '有效牌',
    usefulHelp: '能减少向听数的牌。',
    noUseful: '无有效牌。',
    totalRemaining: '张可用',
    clear: '清空',
    sort: '排序',
    redraw: '重新摸牌',
    drawnTileLabel: '摸到的牌',
    waiting13: '添加牌来构建手牌。',
    error: '错误',
    discard: '打',
    draw: '摸',
    discardAnalysis: '打牌分析',
    discardHelp: '对于每张可打的牌，显示哪些摸牌能改善手牌。',
    count: '枚',
    edit: '编辑',
    expected: '需要',
  },
} as const

// ─── Tile Components ───

function ShantenTile({
  tile,
  onClick,
  size = 'normal',
  selected = false,
  dimmed = false,
  badge,
}: {
  tile: TileValue
  onClick?: () => void
  size?: 'normal' | 'small' | 'palette'
  selected?: boolean
  dimmed?: boolean
  badge?: string
}) {
  const svgName = getTileSvgName(tile)
  const sizeStyle =
    size === 'palette'
      ? { width: 'clamp(2.9rem, 4.6vw, 3.6rem)', height: 'clamp(4.2rem, 6.5vw, 5.2rem)', minWidth: '46px', minHeight: '66px' }
      : size === 'small'
        ? { width: '1.8vw', height: '2.5vw', minWidth: '22px', minHeight: '30px' }
        : undefined

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={dimmed && !selected}
      className={`mahjong-tile ${size === 'small' ? 'small' : ''} rounded-md transition ${selected ? 'ring-2 ring-emerald-400 ring-offset-2 ring-offset-slate-950' : ''} ${dimmed ? 'opacity-30 cursor-not-allowed' : ''}`}
      style={{
        padding: 0,
        border: 'none',
        backgroundColor: 'transparent',
        boxShadow: selected ? '0 0 14px rgba(251,191,36,0.7)' : '1px 1px 3px rgba(0,0,0,0.45)',
        position: 'relative',
        cursor: onClick && !dimmed ? 'pointer' : dimmed ? 'not-allowed' : 'default',
        ...sizeStyle,
      }}
      title={getTileName(tile)}
    >
      <img
        src={`/Regular_shortnames/${svgName}`}
        alt={getTileName(tile)}
        draggable="false"
        style={{ width: '85%', height: '85%', display: 'block', position: 'absolute', top: '7.5%', left: '7.5%', zIndex: 2 }}
      />
      {badge && (
        <span style={{
          position: 'absolute', bottom: '-6px', right: '-6px', zIndex: 10,
          fontSize: '0.65rem', fontWeight: 700, lineHeight: 1, padding: '2px 5px',
          borderRadius: '9999px', backgroundColor: 'rgb(30 41 59)',
          border: '1px solid rgb(51 65 85)', color: 'rgb(148 163 184)',
        }}>
          {badge}
        </span>
      )}
    </button>
  )
}

function HandRow({ tiles, emptyLabel, onTileClick }: {
  tiles: TileDraft[]
  emptyLabel: string
  onTileClick: (id: string) => void
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
        <ShantenTile key={tile.id} tile={tile} onClick={() => onTileClick(tile.id)} />
      ))}
    </div>
  )
}

function PaletteGrid({ onTileClick, usedCounts, selectedTile = null, dimSelected = false }: {
  onTileClick: (tile: TileValue) => void
  usedCounts: Map<string, number>
  selectedTile?: TileValue | null
  dimSelected?: boolean
}) {
  return (
    <div className="flex flex-wrap gap-3 md:gap-4">
      {TILE_LIBRARY.map((tile) => {
        const key = tileKey(tile)
        const remaining = 4 - (usedCounts.get(key) ?? 0)
        const isSelected = sameTile(tile, selectedTile)
        const isDimmed = remaining <= 0 || (dimSelected && isSelected)
        return (
          <ShantenTile
            key={formatTile(tile)}
            tile={tile}
            onClick={() => onTileClick(tile)}
            size="palette"
            selected={isSelected}
            dimmed={isDimmed}
            badge={remaining < 4 ? `${remaining}` : undefined}
          />
        )
      })}
    </div>
  )
}

// ─── Discard analysis table ───

function DiscardAnalysisTable({ options, lang }: {
  options: DiscardOption[]
  lang: Lang
}) {
  const text = TEXT[lang]
  return (
    <div className="rounded-2xl border border-slate-700 bg-slate-950/60 p-4">
      <div className="mb-4">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-emerald-200">{text.discardAnalysis}</h3>
        <p className="text-xs text-slate-400">{text.discardHelp}</p>
      </div>
      <div className="space-y-3">
        {options.map((opt) => {
          const discardKey = `${opt.discard.suit}-${opt.discard.value}`
          const shantenColor =
            opt.shanten === 0 ? 'text-emerald-300' : 'text-slate-300'
          const shantenText =
            opt.shanten === 0 ? (lang === 'zh' ? '听牌' : 'Tenpai') :
            `${opt.shanten}${text.shantenAway}`
          return (
            <div key={discardKey} className="rounded-xl border border-slate-700 bg-slate-900/60 p-3">
              <div className="flex items-center gap-3 flex-wrap">
                {/* Discard tile */}
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-xs font-bold uppercase text-rose-300">{text.discard}</span>
                  <ShantenTile tile={opt.discard} size="small" />
                </div>

                {/* Separator */}
                <div className="h-8 w-px bg-slate-700 shrink-0 hidden sm:block" />

                {/* Shanten badge */}
                <span className={`text-xs font-bold shrink-0 ${shantenColor}`}>
                  {shantenText}
                </span>

                {/* Separator */}
                <div className="h-8 w-px bg-slate-700 shrink-0 hidden sm:block" />

                {/* Draw label */}
                <span className="text-xs font-bold uppercase text-emerald-300 shrink-0">{text.draw}</span>

                {/* Useful tiles row */}
                <div className="flex flex-wrap items-center gap-1.5">
                  {(opt.usefulTiles ?? []).map((t) => (
                    <ShantenTile key={`${t.suit}-${t.value}`} tile={{ suit: t.suit, value: t.value }} size="small" />
                  ))}
                </div>

                {/* Total count */}
                <span className="ml-auto text-sm font-bold text-slate-300 shrink-0">
                  {opt.totalUseful}{lang === 'zh' ? '枚' : ' tiles'}
                </span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ─── Main Page ───

export default function Shanten() {
  const [lang, setLang] = useState<Lang>('en')
  const [hand, setHand] = useState<TileDraft[]>([])
  const [wildTile, setWildTile] = useState<TileValue | null>(null)
  const [openMelds, setOpenMelds] = useState(0)
  const [handInput, setHandInput] = useState('')
  const [wildInput, setWildInput] = useState('')
  const [result, setResult] = useState<ShantenResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showWildPalette, setShowWildPalette] = useState(false)
  const initializedRef = useRef(false)

  const baseSize = 13 - 3 * openMelds
  const text = TEXT[lang]

  // Initialize from URL on mount (run once)
  useEffect(() => {
    if (initializedRef.current) return
    initializedRef.current = true
    const decoded = decodeUrlState(window.location.search)
    if (decoded.hand.length > 0) {
      setHand(decoded.hand.map(createDraft))
      setHandInput(formatHand(decoded.hand))
    }
    if (decoded.wildTile) {
      setWildTile(decoded.wildTile)
      setWildInput(formatTile(decoded.wildTile))
    }
    if (decoded.openMelds > 0) {
      setOpenMelds(decoded.openMelds)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Update URL when state changes (use replaceState to avoid re-renders)
  useEffect(() => {
    if (!initializedRef.current) return
    const tiles = hand.map(t => ({ suit: t.suit, value: t.value }))
    const qs = encodeUrlState(tiles, wildTile, openMelds)
    const newSearch = qs ? `?${qs}` : window.location.pathname
    if (window.location.search !== (qs ? `?${qs}` : '')) {
      window.history.replaceState(null, '', newSearch)
    }
  }, [hand, wildTile, openMelds])

  const usedCounts = useMemo(() => countTiles(hand.map(t => ({ suit: t.suit, value: t.value }))), [hand])

  // Auto-calculate when hand is baseSize or baseSize+1 tiles
  const calculate = useCallback(async (currentHand: TileDraft[], currentWild: TileValue | null, currentMelds: number) => {
    const expected = 13 - 3 * currentMelds
    if (currentHand.length !== expected && currentHand.length !== expected + 1) {
      setResult(null)
      setError(null)
      return
    }

    try {
      const body = {
        closedHand: currentHand.map(t => ({ suit: t.suit, value: t.value })),
        wildTile: currentWild,
        openMelds: currentMelds,
      }
      const resp = await fetch(getApiUrl('/api/v1/tools/shanten'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({ error: 'Request failed' }))
        setError(data.error || `HTTP ${resp.status}`)
        setResult(null)
        return
      }
      const data: ShantenResult = await resp.json()
      setResult(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed')
      setResult(null)
    }
  }, [])

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => calculate(hand, wildTile, openMelds), 150)
    return () => { if (timerRef.current) clearTimeout(timerRef.current) }
  }, [hand, wildTile, openMelds, calculate])

  const maxSize = baseSize + 1
  const addTile = useCallback((tile: TileValue) => {
    if (hand.length >= maxSize) return
    const remaining = remainingCount(tile, usedCounts)
    if (remaining <= 0) return
    setHand(prev => [...prev, createDraft(tile)])
  }, [hand.length, maxSize, usedCounts])

  const removeTile = useCallback((id: string) => {
    setHand(prev => prev.filter(t => t.id !== id))
  }, [])

  const clearHand = useCallback(() => {
    setHand([])
    setHandInput('')
    setResult(null)
    setError(null)
  }, [])

  const doSort = useCallback(() => {
    setHand(prev => sortHand(prev))
  }, [])

  const applyHandInput = useCallback(() => {
    const input = handInput.trim()
    if (!input) return
    const { tiles, error: parseError } = parseHand(input)
    if (parseError) { setError(parseError); return }
    if (tiles.length > maxSize) { setError(`Too many tiles: ${tiles.length} > ${maxSize}`); return }
    const counts = countTiles(tiles)
    for (const [, count] of counts) {
      if (count > 4) { setError('Cannot use more than 4 of the same tile'); return }
    }
    setHand(tiles.map(createDraft))
    setError(null)
  }, [handInput, baseSize])

  const applyWildInput = useCallback(() => {
    const trimmed = wildInput.trim()
    if (!trimmed) { setWildTile(null); return }
    const { tiles, error: parseError } = parseHand(trimmed)
    if (parseError) { setError(parseError); return }
    if (tiles.length !== 1) { setError('Enter exactly one tile for wild (e.g. 9s)'); return }
    setWildTile(tiles[0])
    setShowWildPalette(false)
    setError(null)
  }, [wildInput])

  const selectWild = useCallback((tile: TileValue) => {
    if (sameTile(tile, wildTile)) { setWildTile(null); setWildInput('') }
    else { setWildTile(tile); setWildInput(formatTile(tile)) }
    setShowWildPalette(false)
  }, [wildTile])

  const shantenLabel = useMemo(() => {
    if (!result) return null
    if (result.shanten === 0) return { label: text.tenpai, color: 'text-emerald-300', bg: 'bg-emerald-400/15 border-emerald-400/40' }
    return { label: `${result.shanten}${text.shantenAway}`, color: 'text-slate-200', bg: 'bg-slate-800 border-slate-700' }
  }, [result, text])

  const modeLabel = `${hand.length}/${baseSize}–${maxSize} ${text.tiles}`

  return (
    <PageShell maxWidth="max-w-7xl" className="gap-6">

        {/* Header */}
        <section className="rounded-3xl border border-slate-800 bg-gradient-to-br from-slate-900 via-slate-900 to-slate-950 p-6 shadow-2xl">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <h1 className="text-3xl font-black tracking-tight text-emerald-300">{text.title}</h1>
              <p className="mt-2 max-w-3xl text-sm text-slate-300">{text.subtitle}</p>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <a href="/tools/calc" className="rounded-full border border-slate-700 bg-slate-900 px-4 py-2 text-sm font-semibold text-slate-300 transition hover:bg-slate-800">
                {lang === 'en' ? 'Scoring Calc' : '算分器'}
              </a>
              <button type="button" onClick={() => setLang(l => l === 'en' ? 'zh' : 'en')}
                className="rounded-full border border-emerald-400/40 bg-slate-900 px-4 py-2 text-sm font-semibold text-emerald-200 transition hover:bg-slate-800">
                {text.language}
              </button>
            </div>
          </div>
        </section>

        {/* Hand builder */}
        <section className="rounded-3xl border border-white/10 bg-slate-950/62 backdrop-blur-sm p-5 shadow-xl">
          <div className="mb-4 flex items-start justify-between gap-3">
            <div>
              <h2 className="text-xl font-bold text-slate-100">{text.closedHand}</h2>
              <p className="text-sm text-slate-400">
                {modeLabel} • {openMelds} {text.openMelds}
              </p>
            </div>
            <div className="flex gap-2">
              <button type="button" onClick={doSort}
                className="rounded-full bg-slate-800 px-3 py-2 text-sm font-semibold text-slate-100 transition hover:bg-slate-700">
                {text.sort}
              </button>
              <button type="button" onClick={clearHand}
                className="rounded-full bg-slate-800 px-3 py-2 text-sm font-semibold text-slate-100 transition hover:bg-slate-700">
                {text.clear}
              </button>
            </div>
          </div>

          <div className="mb-4 flex flex-col gap-3 lg:flex-row">
            <input value={handInput} onChange={e => setHandInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && applyHandInput()}
              placeholder="11234455666792p"
              className="w-full rounded-2xl border border-slate-700 bg-slate-950 px-4 py-3 font-mono text-sm text-slate-100 outline-none transition focus:border-emerald-400" />
            <button type="button" onClick={applyHandInput}
              className="rounded-2xl bg-slate-800 px-4 py-3 text-sm font-semibold text-slate-100 transition hover:bg-slate-700">
              {text.apply}
            </button>
          </div>

          <HandRow tiles={hand} emptyLabel={text.noTiles} onTileClick={removeTile} />

          <div className="mt-4 rounded-2xl border border-slate-700 bg-slate-950/60 p-4">
            <div className="mb-3">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-emerald-200">{text.tilePalette}</h3>
              <p className="text-xs text-slate-400">{text.paletteHelp}</p>
            </div>
            <PaletteGrid onTileClick={addTile} usedCounts={usedCounts} />
          </div>
        </section>

        {/* Options row: Wild tile + Open melds */}
        <section className="grid gap-6 lg:grid-cols-2">
          {/* Wild tile */}
          <div className="rounded-3xl border border-white/10 bg-slate-950/62 backdrop-blur-sm p-5 shadow-xl">
            <div className="mb-4 flex items-start justify-between gap-3">
              <div>
                <h2 className="text-xl font-bold text-slate-100">{text.wildTile}</h2>
                <p className="text-sm text-slate-400">{text.wildHelp}</p>
              </div>
              {!showWildPalette && (
                <button type="button" onClick={() => setShowWildPalette(true)}
                  className="rounded-full bg-slate-800 px-3 py-2 text-sm font-semibold text-slate-100 transition hover:bg-slate-700">
                  {text.edit}
                </button>
              )}
            </div>
            <div className="flex min-h-16 items-center justify-center rounded-xl border border-slate-700 bg-slate-950/60 p-3">
              {wildTile ? (
                <ShantenTile tile={wildTile} onClick={() => { setWildTile(null); setWildInput('') }} selected />
              ) : (
                <span className="text-sm text-slate-400">{text.noWild}</span>
              )}
            </div>
            {showWildPalette && (
              <>
                <div className="mt-4 flex gap-3">
                  <input value={wildInput} onChange={e => setWildInput(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && applyWildInput()} placeholder="9s"
                    className="w-full rounded-2xl border border-slate-700 bg-slate-950 px-4 py-3 font-mono text-sm text-slate-100 outline-none transition focus:border-emerald-400" />
                  <button type="button" onClick={applyWildInput}
                    className="rounded-2xl bg-slate-800 px-4 py-3 text-sm font-semibold text-slate-100 transition hover:bg-slate-700">
                    {text.apply}
                  </button>
                </div>
                <div className="mt-4 rounded-2xl border border-slate-700 bg-slate-950/60 p-4">
                  <PaletteGrid onTileClick={selectWild} usedCounts={new Map()} selectedTile={wildTile} dimSelected />
                </div>
              </>
            )}
          </div>

          {/* Open melds count */}
          <div className="rounded-3xl border border-white/10 bg-slate-950/62 backdrop-blur-sm p-5 shadow-xl">
            <div className="mb-4">
              <h2 className="text-xl font-bold text-slate-100">{text.openMeldsLabel}</h2>
              <p className="text-sm text-slate-400">{text.openMeldsHelp}</p>
            </div>
            <div className="flex items-center gap-3">
              {[0, 1, 2, 3, 4].map(n => (
                <button key={n} type="button"
                  onClick={() => {
                    setOpenMelds(n)
                    const newMax = 13 - 3 * n + 1
                    if (hand.length > newMax) setHand(prev => prev.slice(0, newMax))
                  }}
                  className={`flex h-12 w-12 items-center justify-center rounded-xl text-lg font-bold transition ${
                    openMelds === n ? 'bg-emerald-400 text-slate-950' : 'border border-slate-700 bg-slate-950/60 text-slate-300 hover:bg-slate-800'
                  }`}>
                  {n}
                </button>
              ))}
            </div>
            <p className="mt-3 text-xs text-slate-400">
              {text.expected}: {baseSize}–{baseSize + 1} {text.tiles}
            </p>
          </div>
        </section>

        {/* Result section */}
        <section className={`rounded-3xl border p-5 shadow-xl ${shantenLabel?.bg ?? 'border-slate-800 bg-slate-900/70'}`}>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-xl font-bold text-slate-100">{text.result}</h2>
            {shantenLabel && (
              <span className={`rounded-full px-4 py-2 text-lg font-black ${shantenLabel.color}`}>
                {shantenLabel.label}
              </span>
            )}
          </div>

          {error && (
            <div className="mb-4 rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-200">
              {text.error}: {error}
            </div>
          )}

          {result ? (
            <div className="space-y-4">
              {/* Shanten number + drawn tile */}
              <div className="rounded-2xl border border-slate-700 bg-slate-950/60 p-4">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-slate-400">{lang === 'en' ? 'Shanten Number' : '向听数'}</span>
                  <span className={`text-4xl font-black ${
                    result.shanten === 0 ? 'text-emerald-300' : 'text-slate-100'
                  }`}>
                    {result.shanten}
                  </span>
                </div>
                {result.drawnTile && (
                  <div className="mt-3 flex items-center gap-3 border-t border-slate-700 pt-3">
                    <span className="text-sm text-slate-400">{text.drawnTileLabel}:</span>
                    <ShantenTile tile={result.drawnTile} size="small" />
                    <button type="button" onClick={() => calculate(hand, wildTile, openMelds)}
                      className="ml-auto rounded-full bg-slate-800 px-3 py-1.5 text-xs font-semibold text-slate-100 transition hover:bg-slate-700">
                      {text.redraw}
                    </button>
                  </div>
                )}
              </div>

              {/* Discard analysis table */}
              {result.discardOptions && result.discardOptions.length > 0 && (
                <DiscardAnalysisTable options={result.discardOptions} lang={lang} />
              )}
            </div>
          ) : (
            <div className="rounded-2xl border border-dashed border-slate-700 bg-slate-950/60 px-4 py-8 text-center text-sm text-slate-400">
              {hand.length === 0 ? text.waiting13 : text.waiting13}
            </div>
          )}
        </section>
    </PageShell>
  )
}
