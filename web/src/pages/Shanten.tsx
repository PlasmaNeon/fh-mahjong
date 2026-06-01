import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
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
import './ledger-theme.css'

type Lang = 'en' | 'zh'

const TEXT = {
  en: {
    language: '中文',
    title: 'Shanten',
    closedHand: 'Closed hand',
    tiles: 'tiles',
    openMelds: 'open melds',
    apply: 'Apply',
    tilePalette: 'Tile palette',
    noTiles: 'Click tiles below to build your hand.',
    wildTile: 'Wild tile (搭)',
    noWild: 'None set',
    openMeldsLabel: 'Open melds',
    result: 'Result',
    complete: 'Complete',
    tenpai: 'Tenpai',
    shantenAway: '-shanten',
    usefulTiles: 'Useful tiles',
    noUseful: 'No useful tiles.',
    totalRemaining: 'tiles remaining',
    clear: 'Clear',
    sort: 'Sort',
    redraw: 'Redraw',
    drawnTileLabel: 'Drawn tile',
    waiting13: 'Add tiles to build a hand.',
    error: 'Error',
    discard: 'disc',
    draw: 'draw',
    discardAnalysis: 'Discard analysis',
    count: 'count',
    edit: 'Edit',
    expected: 'Expected',
  },
  zh: {
    language: 'EN',
    title: '向听',
    closedHand: '手牌',
    tiles: '张',
    openMelds: '副露',
    apply: '确认',
    tilePalette: '选牌',
    noTiles: '点击下方的牌来构建手牌。',
    wildTile: '搭牌（百搭）',
    noWild: '未设置',
    openMeldsLabel: '副露数',
    result: '结果',
    complete: '和了',
    tenpai: '听牌',
    shantenAway: '向听',
    usefulTiles: '有效牌',
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
    count: '枚',
    edit: '编辑',
    expected: '需要',
  },
} as const

// ─── Tile component ───

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
      disabled={dimmed && !selected}
      title={getTileName(tile)}
    >
      <img src={`/Regular_shortnames/${svgName}`} alt={getTileName(tile)} draggable="false" />
      {badge && <span className="ldg-tile__badge">{badge}</span>}
    </button>
  )
}

// ─── Hand row ───

function HandRow({ tiles, emptyLabel, onTileClick }: {
  tiles: TileDraft[]
  emptyLabel: string
  onTileClick: (id: string) => void
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
        <ShantenTile key={tile.id} tile={tile} onClick={() => onTileClick(tile.id)} />
      ))}
    </div>
  )
}

// ─── Palette grid ───

function PaletteGrid({ onTileClick, usedCounts, selectedTile = null, dimSelected = false }: {
  onTileClick: (tile: TileValue) => void
  usedCounts: Map<string, number>
  selectedTile?: TileValue | null
  dimSelected?: boolean
}) {
  return (
    <div className="ldg-palette-grid">
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

// ─── Main page ───

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
  }, [handInput, baseSize, maxSize])

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

  const shantenStatusLabel = useMemo(() => {
    if (!result) return null
    if (result.shanten === -1) return { label: text.complete, ok: true }
    if (result.shanten === 0) return { label: text.tenpai, ok: true }
    return { label: `${result.shanten}${text.shantenAway}`, ok: false }
  }, [result, text])

  return (
    <div className="ledger-page">
      <div className="ledger-shell">
        <article className="ldg-page">

          {/* Header */}
          <div className="ldg-page-head">
            <div>
              <h1 className="ldg-page-head__title">
                {text.title}
                <small>{lang === 'en' ? '奉化向听' : 'Shanten Calculator'}</small>
              </h1>
            </div>
            <div className="ldg-page-head__nav">
              <button
                type="button"
                className="ldg-link"
                onClick={() => setLang(l => l === 'en' ? 'zh' : 'en')}
              >
                {text.language}
              </button>
              <a href="/tools/calc" className="ldg-link">
                {lang === 'en' ? 'Calculator →' : '算分器 →'}
              </a>
            </div>
          </div>

          {/* Closed hand */}
          <section className="ldg-section">
            <div className="ldg-section-row">
              <h2 className="ldg-section-title">
                {text.closedHand}
                <small>{baseSize}–{maxSize} {text.tiles}</small>
              </h2>
              <span className="ldg-section-meta">{hand.length} / {baseSize}–{maxSize}</span>
            </div>

            <HandRow tiles={hand} emptyLabel={text.noTiles} onTileClick={removeTile} />

            <div className="ldg-input-row">
              <input
                className="ldg-input"
                value={handInput}
                onChange={e => setHandInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && applyHandInput()}
                placeholder="11234455666792p"
              />
              <button type="button" className="ldg-btn" onClick={applyHandInput}>
                {text.apply}
              </button>
            </div>

            <div className="ldg-tools-row ldg-tools-row--end">
              <button type="button" className="ldg-btn" onClick={doSort}>{text.sort}</button>
              <button type="button" className="ldg-btn" onClick={clearHand}>{text.clear}</button>
            </div>

            <div className="ldg-palette-drawer">
              <div className="ldg-palette-drawer__head">{text.tilePalette}</div>
              <PaletteGrid onTileClick={addTile} usedCounts={usedCounts} />
            </div>
          </section>

          {/* Wild tile */}
          <section className="ldg-section">
            <div className="ldg-section-row">
              <h2 className="ldg-section-title">{text.wildTile}</h2>
              <span className="ldg-section-meta">{wildTile ? formatTile(wildTile) : '—'}</span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
              {wildTile ? (
                <ShantenTile
                  tile={wildTile}
                  onClick={() => { setWildTile(null); setWildInput('') }}
                  selected
                />
              ) : (
                <span className="ldg-note" style={{ marginTop: 0 }}>{text.noWild}</span>
              )}
              <button
                type="button"
                className="ldg-link"
                onClick={() => setShowWildPalette(v => !v)}
              >
                {text.edit}
              </button>
            </div>

            {showWildPalette && (
              <>
                <div className="ldg-input-row">
                  <input
                    className="ldg-input"
                    value={wildInput}
                    onChange={e => setWildInput(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && applyWildInput()}
                    placeholder="9s"
                  />
                  <button type="button" className="ldg-btn" onClick={applyWildInput}>
                    {text.apply}
                  </button>
                </div>
                <div className="ldg-palette-drawer">
                  <div className="ldg-palette-drawer__head">{text.tilePalette}</div>
                  <PaletteGrid
                    onTileClick={selectWild}
                    usedCounts={new Map()}
                    selectedTile={wildTile}
                    dimSelected
                  />
                </div>
              </>
            )}
          </section>

          {/* Open melds */}
          <section className="ldg-section">
            <div className="ldg-section-row">
              <h2 className="ldg-section-title">{text.openMeldsLabel}</h2>
              <span className="ldg-section-meta">{openMelds}</span>
            </div>
            <div className="ldg-chooser">
              {[0, 1, 2, 3, 4].map(n => (
                <button
                  key={n}
                  type="button"
                  className={`ldg-chooser__btn${openMelds === n ? ' is-active' : ''}`}
                  onClick={() => {
                    setOpenMelds(n)
                    const newMax = 13 - 3 * n + 1
                    if (hand.length > newMax) setHand(prev => prev.slice(0, newMax))
                  }}
                >
                  {n}
                </button>
              ))}
            </div>
            <p className="ldg-note">
              {text.expected}: {baseSize}–{baseSize + 1} {text.tiles}
            </p>
          </section>

          {/* Result */}
          <section className="ldg-result">
            <div className="ldg-result-row">
              <div className="ldg-result-label">{text.result}</div>
              {shantenStatusLabel && (
                <div className={`ldg-result-status${shantenStatusLabel.ok ? ' ldg-result-status--ok' : ''}`}>
                  {shantenStatusLabel.label}
                </div>
              )}
            </div>

            {error && (
              <p className="ldg-note ldg-note--err">{text.error}: {error}</p>
            )}

            {result ? (
              <>
                <div className="ldg-big-stat">
                  <div className="ldg-big-stat__label">
                    {lang === 'en' ? 'Shanten' : '向听数'}
                  </div>
                  <div className={`ldg-big-stat__value${result.shanten <= 0 ? ' ldg-big-stat__value--accent' : ''}`}>
                    {result.shanten}
                  </div>
                </div>

                {result.drawnTile && (
                  <p className="ldg-note" style={{ marginTop: '1rem' }}>
                    {text.drawnTileLabel}
                    {' '}
                    <span style={{ display: 'inline-flex', verticalAlign: 'middle', margin: '0 0.2rem' }}>
                      <ShantenTile tile={result.drawnTile} size="small" />
                    </span>
                    {' · '}
                    <button
                      type="button"
                      className="ldg-link"
                      onClick={() => calculate(hand, wildTile, openMelds)}
                    >
                      {text.redraw}
                    </button>
                  </p>
                )}

                {result.discardOptions && result.discardOptions.length > 0 && (
                  <div style={{ marginTop: '2rem' }}>
                    <div className="ldg-result-row" style={{ marginBottom: '0.75rem' }}>
                      <div className="ldg-result-label">{text.discardAnalysis}</div>
                    </div>
                    {result.discardOptions.map((opt: DiscardOption) => {
                      const discardKey = `${opt.discard.suit}-${opt.discard.value}`
                      const shantenText = opt.shanten === 0
                        ? (lang === 'zh' ? '听牌' : 'tenpai')
                        : `${opt.shanten}${text.shantenAway}`
                      return (
                        <div key={discardKey} className="ldg-discard-row">
                          <span>
                            <span className="ldg-discard-row__tag">{text.discard}</span>
                            <ShantenTile tile={opt.discard} size="small" />
                          </span>
                          <span className="ldg-discard-row__shanten">{shantenText}</span>
                          <span className="ldg-discard-row__draws">
                            {(opt.usefulTiles ?? []).map(t => (
                              <ShantenTile
                                key={`${t.suit}-${t.value}`}
                                tile={{ suit: t.suit, value: t.value }}
                                size="small"
                              />
                            ))}
                          </span>
                          <span className="ldg-discard-row__count">
                            {opt.totalUseful}{lang === 'zh' ? '枚' : ''}
                          </span>
                        </div>
                      )
                    })}
                  </div>
                )}
              </>
            ) : (
              !error && <p className="ldg-note">{text.waiting13}</p>
            )}
          </section>

        </article>
      </div>
    </div>
  )
}
