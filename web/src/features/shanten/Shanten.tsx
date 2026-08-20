import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { getApiUrl } from '../../config'
import { ClubShell, InputApplyRow, LedgerPaletteGrid, LedgerTile, LedgerTileRow, ToolTabs } from '../../theme'
import { useI18n } from '../../i18n/I18nContext'
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
  TileValue,
} from './shantenHelpers'

// ─── Main page ───

export default function Shanten() {
  const { t, shortLanguage: lang, toggleLanguage } = useI18n()
  const [hand, setHand] = useState<TileDraft[]>([])
  const [wildTile, setWildTile] = useState<TileValue | null>(null)
  const [openMelds, setOpenMelds] = useState(0)
  const [handInput, setHandInput] = useState('')
  const [wildInput, setWildInput] = useState('')
  const [result, setResult] = useState<ShantenResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [paletteTarget, setPaletteTarget] = useState<'hand' | 'wild'>('hand')
  const initializedRef = useRef(false)

  const baseSize = 13 - 3 * openMelds

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
    setError(null)
  }, [wildInput])

  const selectWild = useCallback((tile: TileValue) => {
    if (sameTile(tile, wildTile)) { setWildTile(null); setWildInput('') }
    else { setWildTile(tile); setWildInput(formatTile(tile)) }
  }, [wildTile])

  const shantenStatusLabel = useMemo(() => {
    if (!result) return null
    if (result.shanten === -1) return { label: t('shanten.complete'), ok: true }
    if (result.shanten === 0) return { label: t('shanten.tenpai'), ok: true }
    return { label: `${result.shanten}${t('shanten.shantenAway')}`, ok: false }
  }, [result, t])

  return (
    <ClubShell title={t('nav.tools')}>
        <article className="ldg-page ldg-page--workbench">

          <ToolTabs />

          {/* Header */}
          <div className="ldg-page-head">
            <div>
              <h1 className="ldg-page-head__title">
                {t('shanten.title')}
                <small>{lang === 'en' ? '奉化向听' : 'Shanten Calculator'}</small>
              </h1>
            </div>
            <div className="ldg-page-head__nav">
              <button
                type="button"
                className="ldg-link"
                onClick={toggleLanguage}
              >
                {t('shanten.language')}
              </button>
            </div>
          </div>

          {/* Closed hand */}
          <section className="ldg-section">
            <div className="ldg-section-row">
              <h2 className="ldg-section-title">
                {t('tools.closedHand')}
                <small>{baseSize}–{maxSize} {t('tools.tiles')}</small>
              </h2>
              <span className="ldg-section-meta">{hand.length} / {baseSize}–{maxSize}</span>
            </div>

            <LedgerTileRow tiles={hand} emptyLabel={t('shanten.noTiles')} onTileClick={removeTile} />

            <InputApplyRow
              value={handInput}
              onChange={setHandInput}
              onApply={applyHandInput}
              applyLabel={t('shanten.apply')}
              placeholder="11234455666792p"
              submitOnEnter
            />

            <div className="ldg-tools-row ldg-tools-row--end">
              <button type="button" className="ldg-btn" onClick={doSort}>{t('shanten.sort')}</button>
              <button type="button" className="ldg-btn" onClick={clearHand}>{t('tools.clear')}</button>
            </div>

          </section>

          {/* Wild tile */}
          <section className="ldg-section">
            <div className="ldg-section-row">
              <h2 className="ldg-section-title">{t('shanten.wildTile')}</h2>
              <span className="ldg-section-meta">{wildTile ? formatTile(wildTile) : '—'}</span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
              {wildTile ? (
                <LedgerTile
                  tile={wildTile}
                  onClick={() => { setWildTile(null); setWildInput('') }}
                  selected
                />
              ) : (
                <span className="ldg-note" style={{ marginTop: 0 }}>{t('shanten.noWild')}</span>
              )}
              <button
                type="button"
                className="ldg-link"
                onClick={() => setPaletteTarget('wild')}
              >
                {t('tools.edit')}
              </button>
            </div>

            {paletteTarget === 'wild' && (
                <InputApplyRow
                  value={wildInput}
                  onChange={setWildInput}
                  onApply={applyWildInput}
                  applyLabel={t('shanten.apply')}
                  placeholder="9s"
                  submitOnEnter
                />
            )}
          </section>

          <section className="ldg-section workbench-palette">
            <div className="ldg-section-row">
              <h2 className="ldg-section-title">{t('tools.tileTray')}<small>{t('shanten.tileTrayHelp')}</small></h2>
            </div>
            <div className="ldg-chooser" aria-label={t('tools.tileTarget')}>
              <button type="button" className={`ldg-chooser__btn${paletteTarget === 'hand' ? ' is-active' : ''}`} onClick={() => setPaletteTarget('hand')}>{t('tools.closedHand')}</button>
              <button type="button" className={`ldg-chooser__btn${paletteTarget === 'wild' ? ' is-active' : ''}`} onClick={() => setPaletteTarget('wild')}>{t('shanten.wildTile')}</button>
            </div>
            <div className="ldg-palette-drawer">
              <div className="ldg-palette-drawer__head">{t('tools.addingTo')} {paletteTarget === 'hand' ? t('tools.closedHand') : t('shanten.wildTile')}</div>
              <LedgerPaletteGrid onTileClick={paletteTarget === 'hand' ? addTile : selectWild} usedCounts={paletteTarget === 'hand' ? usedCounts : new Map()} selectedTile={paletteTarget === 'wild' ? wildTile : null} dimSelected={paletteTarget === 'wild'} />
            </div>
          </section>

          <details className="advanced-setup">
          <summary>{t('tools.advancedSetup')} <span>{t('shanten.advancedSetupHelp')}</span></summary>
          {/* Open melds */}
          <section className="ldg-section">
            <div className="ldg-section-row">
              <h2 className="ldg-section-title">{t('shanten.openMeldsLabel')}</h2>
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
              {t('shanten.expected')}: {baseSize}–{baseSize + 1} {t('tools.tiles')}
            </p>
          </section>
          </details>

          <div className="ldg-actions-row">
            <div className="ldg-validation-area">
              <span className="ldg-note" style={{ marginTop: 0 }}>{hand.length} / {baseSize}–{maxSize} {t('tools.tiles')}</span>
            </div>
            <button type="button" className="ldg-btn ldg-btn--primary" onClick={() => calculate(hand, wildTile, openMelds)}>
              {lang === 'en' ? 'Analyze Hand' : '分析手牌'}
            </button>
          </div>

          {/* Result */}
          <section className="ldg-result">
            <div className="ldg-result-row">
              <div className="ldg-result-label">{t('tools.result')}</div>
              {shantenStatusLabel && (
                <div className={`ldg-result-status${shantenStatusLabel.ok ? ' ldg-result-status--ok' : ''}`}>
                  {shantenStatusLabel.label}
                </div>
              )}
            </div>

            {error && (
              <p className="ldg-note ldg-note--err">{t('shanten.error')}: {error}</p>
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
                    {t('shanten.drawnTileLabel')}
                    {' '}
                    <span style={{ display: 'inline-flex', verticalAlign: 'middle', margin: '0 0.2rem' }}>
                      <LedgerTile tile={result.drawnTile} size="small" />
                    </span>
                    {' · '}
                    <button
                      type="button"
                      className="ldg-link"
                      onClick={() => calculate(hand, wildTile, openMelds)}
                    >
                      {t('shanten.redraw')}
                    </button>
                  </p>
                )}

                {result.discardOptions && result.discardOptions.length > 0 && (
                  <div style={{ marginTop: '2rem' }}>
                    <div className="ldg-result-row" style={{ marginBottom: '0.75rem' }}>
                      <div className="ldg-result-label">{t('shanten.discardAnalysis')}</div>
                    </div>
                    {result.discardOptions.map((opt: DiscardOption) => {
                      const discardKey = `${opt.discard.suit}-${opt.discard.value}`
                      const shantenText = opt.shanten === 0
                        ? (lang === 'zh' ? '听牌' : 'tenpai')
                        : `${opt.shanten}${t('shanten.shantenAway')}`
                      return (
                        <div key={discardKey} className="ldg-discard-row">
                          <span>
                            <span className="ldg-discard-row__tag">{t('shanten.discard')}</span>
                            <LedgerTile tile={opt.discard} size="small" />
                          </span>
                          <span className="ldg-discard-row__shanten">{shantenText}</span>
                          <span className="ldg-discard-row__draws">
                            {(opt.usefulTiles ?? []).map(t => (
                              <LedgerTile
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
              !error && <p className="ldg-note">{t('shanten.waiting13')}</p>
            )}
          </section>

        </article>
    </ClubShell>
  )
}
