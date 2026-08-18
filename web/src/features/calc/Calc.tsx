import { useEffect, useState } from 'react'

import { getApiUrl, hasConfiguredApiBaseUrl } from '../../config'
import { game } from '../../proto/game'
import { ClubShell, InputApplyRow, LedgerPaletteGrid, LedgerTile, LedgerTileRow, ToolTabs } from '../../theme'
import { useI18n } from '../../i18n/I18nContext'
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
  sortTiles,
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

const KONG_FLAG_OPTIONS: Array<{ key: keyof CalcKongFlags; label: string }> = [
  { key: 'hasBuddingDirectKong', label: 'Budding Direct Kong' },
  { key: 'hasBloomingDirectKong', label: 'Blooming Direct Kong' },
  { key: 'hasBuddingClosedKong', label: 'Budding Closed Kong' },
  { key: 'hasBloomingClosedKong', label: 'Blooming Closed Kong' },
  { key: 'hasBuddingRiskyKong', label: 'Budding Risky Kong' },
  { key: 'hasBloomingRiskyKong', label: 'Blooming Risky Kong' },
]

const MELD_TYPE_OPTIONS = [
  { value: game.ActionType.ACTION_CHII, label: 'Chii' },
  { value: game.ActionType.ACTION_PON, label: 'Pon' },
  { value: game.ActionType.ACTION_KAN, label: 'Kan' },
]

const MELD_DIRECTION_OPTIONS = [
  { value: game.MeldDirection.MELD_DIRECTION_UNKNOWN, label: 'Self' },
  { value: game.MeldDirection.MELD_DIRECTION_RIGHT, label: 'Right' },
  { value: game.MeldDirection.MELD_DIRECTION_ACROSS, label: 'Across' },
  { value: game.MeldDirection.MELD_DIRECTION_LEFT, label: 'Left' },
]

// ─── Tile component ───

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

function getMeldLabelForLang(type: game.ActionType, lang: Lang): string {
  const label = getMeldLabel(type)
  if (lang === 'en') return label
  switch (label) {
    case 'Chii': return '吃'
    case 'Pon': return '碰'
    case 'Kan': return '杠'
    default: return label
  }
}

function getDirectionLabelForLang(direction: game.MeldDirection, lang: Lang): string {
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
  const { t, shortLanguage: lang, toggleLanguage } = useI18n()
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
  const [paletteTarget, setPaletteTarget] = useState<'hand' | 'win' | 'wild' | 'meld'>('hand')

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

  const addMeld = (type: game.ActionType) => {
    const nextMeld = createMeldDraft(type)
    setOpenMelds((current) => [...current, nextMeld])
    setActiveMeldId(nextMeld.id)
    clearServerState()
  }

  const updateMeldType = (meldId: string, type: game.ActionType) => {
    setOpenMelds((current) =>
      current.map((meld) => {
        if (meld.id !== meldId) return meld
        const requiredCount = meldRequiredTileCount(type)
        const nextTiles = meld.tiles.slice(0, requiredCount)
        const nextCalledTileIndex = nextTiles.length === 0 ? 0 : Math.min(meld.calledTileIndex, nextTiles.length - 1)
        return {
          ...meld, type, tiles: nextTiles, calledTileIndex: nextCalledTileIndex,
          calledDirection: type === game.ActionType.ACTION_CHII ? game.MeldDirection.MELD_DIRECTION_LEFT : meld.calledDirection,
          kongContext: type === game.ActionType.ACTION_KAN ? meld.kongContext : '',
        }
      }),
    )
    clearServerState()
  }

  const updateMeldDirection = (meldId: string, direction: game.MeldDirection) => {
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
          ? { ...meld, tiles: [], calledTileIndex: 0, kongContext: meld.type === game.ActionType.ACTION_KAN ? '' : meld.kongContext }
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
        if (meld.id !== meldId || meld.type !== game.ActionType.ACTION_KAN) return meld
        const isClosedKong = value === 'hasBuddingClosedKong' || value === 'hasBloomingClosedKong'
        return {
          ...meld, kongContext: value,
          calledDirection: isClosedKong ? game.MeldDirection.MELD_DIRECTION_UNKNOWN : meld.calledDirection,
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

  const addPaletteTile = (tile: CalcTileValue) => {
    if (paletteTarget === 'hand') addTileToClosedHand(tile)
    if (paletteTarget === 'win') { setWinTile(createTileDraft(tile)); clearServerState() }
    if (paletteTarget === 'wild') { setWildTile(createTileDraft(tile)); clearServerState() }
    if (paletteTarget === 'meld' && activeMeldId) addTileToMeld(activeMeldId, tile)
  }

  return (
    <ClubShell wide title={t('nav.tools')}>
        <article className="ldg-page ldg-page--workbench">

          <ToolTabs />

          {/* Header */}
          <div className="ldg-page-head">
            <div>
              <h1 className="ldg-page-head__title">
                {t('calc.title')}
                <small>{lang === 'en' ? '奉化算分器' : 'Fenghua Calculator'}</small>
              </h1>
            </div>
            <div className="ldg-page-head__nav">
              <button
                type="button"
                className="ldg-link"
                onClick={toggleLanguage}
              >
                {t('calc.language')}
              </button>
            </div>
          </div>

          {/* Closed hand */}
          <section className="ldg-section">
            <div className="ldg-section-row">
              <h2 className="ldg-section-title">
                {t('tools.closedHand')}
                <small>{t('calc.expectedCount')} {expectedHandLength} {t('tools.tiles')}</small>
              </h2>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <span className="ldg-section-meta">{closedHand.length} / {expectedHandLength}</span>
                {collapsedSections.closedHand && (
                  <button
                    type="button"
                    className="ldg-link"
                    onClick={() => setCollapsedSections((current) => ({ ...current, closedHand: false }))}
                  >
                    {t('tools.edit')}
                  </button>
                )}
              </div>
            </div>

            {!collapsedSections.closedHand && (
              <InputApplyRow
                value={closedHandInput}
                onChange={setClosedHandInput}
                onApply={applyClosedHandInput}
                applyLabel={t('calc.apply')}
                placeholder="1m2m3m 4p5p6p 7s8s9s 3z"
              />
            )}

            <LedgerTileRow tiles={closedHand} emptyLabel={t('calc.noClosedHand')} onTileClick={removeClosedHandTile} />

          </section>

          {/* Win tile + Wild tile */}
          <div className="ldg-grid-2" style={{ marginTop: 'var(--space)' }}>
            {/* Win tile */}
            <div>
              <div className="ldg-section-row" style={{ marginBottom: '0.85rem' }}>
                <h2 className="ldg-section-title">{t('calc.winTile')}</h2>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                  {collapsedSections.winTile && winTile && (
                    <LedgerTile tile={winTile} onClick={() => { setWinTile(null); clearServerState() }} size="small" />
                  )}
                  {collapsedSections.winTile && (
                    <button
                      type="button"
                      className="ldg-link"
                      onClick={() => setCollapsedSections((current) => ({ ...current, winTile: false }))}
                    >
                      {t('tools.edit')}
                    </button>
                  )}
                </div>
              </div>

              {!collapsedSections.winTile && (
                <>
                  <InputApplyRow
                    value={winTileInput}
                    onChange={setWinTileInput}
                    onApply={applyWinTileInput}
                    applyLabel={t('calc.apply')}
                    placeholder="3z"
                  />
                  {!winTile && (
                    <p className="ldg-note">{t('calc.noWinTile')}</p>
                  )}
                </>
              )}
            </div>

            {/* Wild tile */}
            <div>
              <div className="ldg-section-row" style={{ marginBottom: '0.85rem' }}>
                <h2 className="ldg-section-title">{t('calc.wildTile')}</h2>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                  {collapsedSections.wildTile && wildTile && (
                    <LedgerTile tile={wildTile} onClick={() => { setWildTile(null); clearServerState() }} size="small" selected />
                  )}
                  {collapsedSections.wildTile && (
                    <button
                      type="button"
                      className="ldg-link"
                      onClick={() => setCollapsedSections((current) => ({ ...current, wildTile: false }))}
                    >
                      {t('tools.edit')}
                    </button>
                  )}
                </div>
              </div>

              {!collapsedSections.wildTile && (
                <>
                  <InputApplyRow
                    value={wildTileInput}
                    onChange={setWildTileInput}
                    onApply={applyWildTileInput}
                    applyLabel={t('calc.apply')}
                    placeholder="9s"
                  />
                  {!wildTile && (
                    <p className="ldg-note">{t('calc.noWildTile')}</p>
                  )}
                </>
              )}
            </div>
          </div>

          <section className="ldg-section workbench-palette">
            <div className="ldg-section-row">
              <h2 className="ldg-section-title">{t('tools.tileTray')}<small>{t('calc.tileTrayHelp')}</small></h2>
            </div>
            <div className="ldg-chooser" aria-label={t('tools.tileTarget')}>
              {([['hand', t('tools.closedHand')], ['win', t('calc.winTile')], ['wild', t('calc.wildTile')], ['meld', t('calc.openMeldsTitle')]] as const).map(([value, label]) => (
                <button key={value} type="button" disabled={value === 'meld' && !activeMeldId} className={`ldg-chooser__btn${paletteTarget === value ? ' is-active' : ''}`} onClick={() => setPaletteTarget(value)}>{label}</button>
              ))}
            </div>
            <div className="ldg-palette-drawer">
              <div className="ldg-palette-drawer__head">{t('tools.addingTo')} {paletteTarget === 'hand' ? t('tools.closedHand') : paletteTarget === 'win' ? t('calc.winTile') : paletteTarget === 'wild' ? t('calc.wildTile') : t('calc.openMeldsTitle')}</div>
              <LedgerPaletteGrid onTileClick={addPaletteTile} selectedTile={paletteTarget === 'win' ? winTile : paletteTarget === 'wild' ? wildTile : null} dimSelected={paletteTarget === 'wild'} />
            </div>
          </section>

          <details className="advanced-setup">
          <summary>{t('tools.advancedSetup')} <span>{t('calc.advancedSetupHelp')}</span></summary>
          {/* Open melds */}
          <section className="ldg-section">
            <div className="ldg-section-row">
              <h2 className="ldg-section-title">{t('calc.openMeldsTitle')}</h2>
              <span className="ldg-section-meta">{openMelds.length}</span>
            </div>

            {openMelds.length === 0 ? (
              <p className="ldg-note">{t('calc.noOpenMelds')}</p>
            ) : (
              openMelds.map((meld, index) => {
                const meldError = validateMeldShape(meld)
                const isActive = activeMeldId === meld.id
                return (
                  <div key={meld.id} className={`ldg-meld${isActive ? ' ldg-meld--active' : ''}`}>
                    <div className="ldg-meld__head">
                      <div>
                        <p className="ldg-meld__title">{t('calc.openMeld')} {index + 1}</p>
                        <p className="ldg-meld__meta">
                          {meld.tiles.length}/{meldRequiredTileCount(meld.type)} {t('tools.tiles')}
                          {' · '}{getDirectionLabelForLang(meld.calledDirection, lang)}
                        </p>
                      </div>
                      <div className="ldg-meld__actions">
                        <button
                          type="button"
                          className={`ldg-btn${isActive ? ' ldg-btn--primary' : ''}`}
                          onClick={() => { setActiveMeldId(isActive ? null : meld.id); if (!isActive) setPaletteTarget('meld') }}
                        >
                          {t('calc.usePalette')}
                        </button>
                        <button type="button" className="ldg-btn" onClick={() => clearMeld(meld.id)}>
                          {t('tools.clear')}
                        </button>
                        <button type="button" className="ldg-btn ldg-btn--danger" onClick={() => removeMeld(meld.id)}>
                          {t('calc.remove')}
                        </button>
                      </div>
                    </div>

                    <div className="ldg-grid-3" style={{ marginBottom: '0.75rem' }}>
                      <div className="ldg-field">
                        <label className="ldg-field__label">{t('calc.meldType')}</label>
                        <select
                          className="ldg-select"
                          value={meld.type}
                          onChange={(event) => updateMeldType(meld.id, Number(event.target.value) as game.ActionType)}
                        >
                          {MELD_TYPE_OPTIONS.map((option) => (
                            <option key={option.value} value={option.value}>
                              {getMeldLabelForLang(option.value, lang)}
                            </option>
                          ))}
                        </select>
                      </div>

                      <div className="ldg-field">
                        <label className="ldg-field__label">{t('calc.calledDirection')}</label>
                        <select
                          className="ldg-select"
                          value={meld.calledDirection}
                          onChange={(event) => updateMeldDirection(meld.id, Number(event.target.value) as game.MeldDirection)}
                          disabled={
                            meld.type === game.ActionType.ACTION_CHII ||
                            (meld.type === game.ActionType.ACTION_KAN &&
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
                        <label className="ldg-field__label">{t('calc.calledTile')}</label>
                        <select
                          className="ldg-select"
                          value={meld.calledTileIndex}
                          onChange={(event) => updateMeldCalledTileIndex(meld.id, Number(event.target.value))}
                          disabled={meld.tiles.length === 0}
                        >
                          {meld.tiles.length === 0 ? (
                            <option value={0}>{t('calc.addTilesFirst')}</option>
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

                    <LedgerTileRow
                      tiles={meld.tiles}
                      emptyLabel={t('calc.meldEmpty')}
                      onTileClick={(tileId) => removeMeldTile(meld.id, tileId)}
                    />

                    {meld.type === game.ActionType.ACTION_KAN && (
                      <div className="ldg-field" style={{ marginTop: '0.75rem' }}>
                        <label className="ldg-field__label">{t('calc.kanContext')}</label>
                        <select
                          className="ldg-select"
                          value={meld.kongContext}
                          onChange={(event) => updateMeldKongContext(meld.id, event.target.value as CalcKongContextKey)}
                        >
                          <option value="">{t('calc.noKanContext')}</option>
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
              <h2 className="ldg-section-title">{t('calc.roundContext')}</h2>
            </div>

            <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap', marginBottom: '1rem' }}>
              <span className="ldg-section-title" style={{ fontSize: '0.85rem', color: 'var(--ink-3)' }}>
                {t('calc.winType')}
              </span>
              <div className="ldg-toggle">
                <button
                  type="button"
                  className={`ldg-toggle__btn${isTsumo ? ' is-active' : ''}`}
                  onClick={() => { setIsTsumo(true); clearServerState() }}
                >
                  {t('calc.tsumo')}
                </button>
                <button
                  type="button"
                  className={`ldg-toggle__btn${!isTsumo ? ' is-active' : ''}`}
                  onClick={() => { setIsTsumo(false); clearServerState() }}
                >
                  {t('calc.ron')}
                </button>
              </div>
            </div>

            <div className="ldg-grid-2">
              <div className="ldg-field">
                <label className="ldg-field__label">{t('calc.seatWind')}</label>
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
                <label className="ldg-field__label">{t('calc.prevailingWind')}</label>
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
              <div className="ldg-check-row__label">{t('calc.flowerKong')}</div>
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
              <h2 className="ldg-section-title">{t('calc.flowerMelds')}</h2>
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

          </details>

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
                <span className="ldg-note ldg-note--ok" style={{ marginTop: 0 }}>{t('calc.noValidationErrors')}</span>
              )}
            </div>
            <button
              type="button"
              className="ldg-btn ldg-btn--primary"
              onClick={handleCalculate}
              disabled={isSubmitting}
            >
              {isSubmitting ? t('calc.calculating') : t('calc.calculatePoints')}
            </button>
          </div>

          {/* Result */}
          <section className="ldg-result">
            <div className="ldg-result-row">
              <div className="ldg-result-label">{t('tools.result')}</div>
              <div className={`ldg-result-status${
                result
                  ? result.canWin ? ' ldg-result-status--ok' : ' ldg-result-status--err'
                  : ''
              }`}>
                {result
                  ? result.canWin ? t('calc.validHand') : t('calc.invalidHand')
                  : t('calc.awaitingEvaluation')}
              </div>
            </div>

            {result ? (
              <>
                <div className="ldg-big-stat">
                  <div className="ldg-big-stat__label">{t('calc.totalScore')}</div>
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
                  <p className="ldg-note">{t('calc.noEntries')}</p>
                )}
              </>
            ) : (
              <p className="ldg-note">{t('calc.submitToSeeResult')}</p>
            )}
          </section>

          {/* Normalized debug (collapsible) */}
          <div className="ldg-footnote">
            <button
              type="button"
              className="ldg-footnote__toggle"
              onClick={() => setShowDebug(v => !v)}
            >
              {showDebug ? '▴' : '▾'} {showDebug ? t('calc.hideDebug') : t('calc.showDebug')}
            </button>

            {showDebug && result && (
              <div style={{ marginTop: '1.25rem' }}>
                <div className="ldg-grid-2" style={{ gap: '0.6rem' }}>
                  <div className="ldg-debug">
                    <div className="ldg-debug__label">{t('tools.closedHand')}</div>
                    <div className="ldg-debug__value">{result.normalized.closedHand || t('calc.none')}</div>
                  </div>
                  <div className="ldg-debug">
                    <div className="ldg-debug__label">{t('calc.winTile')}</div>
                    <div className="ldg-debug__value">{result.normalized.winTile || t('calc.none')}</div>
                  </div>
                  <div className="ldg-debug">
                    <div className="ldg-debug__label">{t('calc.wildTile')}</div>
                    <div className="ldg-debug__value">{result.normalized.wildTile || t('calc.none')}</div>
                  </div>
                  <div className="ldg-debug">
                    <div className="ldg-debug__label">{t('calc.context')}</div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.4rem', marginTop: '0.2rem' }}>
                      <div className="ldg-kv">
                        <div className="ldg-kv__key">{t('calc.winType')}</div>
                        <div className="ldg-kv__val">{localizeDebugValue(result.normalized.winType, lang) || t('calc.none')}</div>
                      </div>
                      <div className="ldg-kv">
                        <div className="ldg-kv__key">{t('calc.seatWind')}</div>
                        <div className="ldg-kv__val">{localizeDebugValue(result.normalized.seatWind, lang) || t('calc.none')}</div>
                      </div>
                      <div className="ldg-kv">
                        <div className="ldg-kv__key">{t('calc.prevailingWind')}</div>
                        <div className="ldg-kv__val">{localizeDebugValue(result.normalized.prevailingWind, lang) || t('calc.none')}</div>
                      </div>
                      <div className="ldg-kv">
                        <div className="ldg-kv__key">{t('calc.expectedClosedHandLength')}</div>
                        <div className="ldg-kv__val">{result.normalized.expectedHandLen}</div>
                      </div>
                    </div>
                  </div>
                </div>

                {result.normalized.openMelds.length > 0 && (
                  <div className="ldg-debug" style={{ marginTop: '0.6rem' }}>
                    <div className="ldg-debug__label">{t('calc.openMeldsTitle')}</div>
                    {result.normalized.openMelds.map((meld, index) => (
                      <div key={`${meld.type}-${meld.tiles}-${index}`} style={{ marginTop: '0.5rem', fontSize: '0.85rem' }}>
                        <div style={{ fontFamily: 'var(--mono)', color: 'var(--ink-2)' }}>
                          {localizeDebugValue(meld.type, lang)}({meld.tiles})
                          {' · '}{t('calc.calledTile')} {meld.calledTile} #{meld.calledTileIndex + 1}
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
                    <div className="ldg-debug__label">{t('calc.flowerMelds')}</div>
                    {result.normalized.flowerMelds.length === 0 ? (
                      <span className="ldg-debug__value">{t('calc.none')}</span>
                    ) : (
                      <div className="ldg-chips-row">
                        {result.normalized.flowerMelds.map((flower) => (
                          <span key={flower} className="ldg-chip">{flower}</span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="ldg-debug">
                    <div className="ldg-debug__label">{t('calc.kanContext')}</div>
                    {result.normalized.kongFlags.length === 0 ? (
                      <span className="ldg-debug__value">{t('calc.none')}</span>
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
              <p className="ldg-note" style={{ marginTop: '0.75rem' }}>{t('calc.evaluateToCapture')}</p>
            )}
          </div>

        </article>
    </ClubShell>
  )
}
