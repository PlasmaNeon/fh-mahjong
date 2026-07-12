import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { TableRoundResultOverlay } from '../../table/TableScene'
import {
  SCENARIO_KEYS,
  SCENARIO_LABELS,
  buildScenario,
  type ScenarioKey,
} from './roundResultScenarios'

// Dev-only preview for PR #152's round-result overlay. Route: /tools/round-result.
// Default = control panel + resizable iframe. The iframe loads this same route
// with ?embed=1 so its own viewport drives the responsive media queries.

const VIEWPORTS = [
  { key: 'phone', label: 'Portrait phone', width: 393, height: 852 },
  { key: 'landscape', label: 'Landscape', width: 852, height: 393 },
  { key: 'desktop', label: 'Desktop', width: 1280, height: 800 },
] as const
type ViewportKey = (typeof VIEWPORTS)[number]['key']

function isScenarioKey(value: string | null): value is ScenarioKey {
  return value !== null && (SCENARIO_KEYS as readonly string[]).includes(value)
}

// ── Embed mode: only the overlay, over a felt backdrop ──────────────────────
function EmbeddedOverlay() {
  const [params] = useSearchParams()
  const raw = params.get('scenario')
  const scenario: ScenarioKey = isScenarioKey(raw) ? raw : 'tsumo'
  const ready = params.get('ready') === '1'
  const [isReady, setIsReady] = useState(false)

  const data = useMemo(() => buildScenario(scenario, ready), [scenario, ready])

  const result = {
    ...data,
    actions: (
      <>
        <button
          onClick={() => setIsReady(true)}
          disabled={isReady}
          className={`round-result-action-btn round-result-action-btn-ready ${isReady ? 'round-result-action-btn-disabled' : ''}`}
        >
          {isReady ? 'Waiting...' : 'Ready'}
        </button>
        <button
          onClick={() => window.alert('Exit is a no-op in the demo.')}
          className="round-result-action-btn round-result-action-btn-exit"
        >
          Exit
        </button>
      </>
    ),
  }

  return (
    <div
      style={{
        minHeight: '100dvh',
        background: 'radial-gradient(circle at 50% 30%, #0f4a3c 0%, #071d1a 72%)',
      }}
    >
      <TableRoundResultOverlay result={result} />
    </div>
  )
}

// ── Playground mode: controls + iframe ──────────────────────────────────────
function segButton(active: boolean): string {
  return [
    'px-3 py-1.5 rounded-md text-sm font-semibold border transition-colors',
    active
      ? 'bg-emerald-500 border-emerald-400 text-emerald-950'
      : 'bg-white/5 border-white/15 text-white/80 hover:bg-white/10',
  ].join(' ')
}

function Playground() {
  const [scenario, setScenario] = useState<ScenarioKey>('tsumo')
  const [viewport, setViewport] = useState<ViewportKey>('phone')
  const [ready, setReady] = useState(false)

  const vp = VIEWPORTS.find((v) => v.key === viewport) ?? VIEWPORTS[0]
  const src = `/tools/round-result?embed=1&scenario=${scenario}&ready=${ready ? '1' : '0'}`

  return (
    <div className="min-h-screen p-6 flex flex-col gap-5">
      <header className="flex flex-col gap-1">
        <h1 className="text-xl font-bold">Round-result payout preview</h1>
        <p className="text-sm text-white/60">
          Dev-only preview of the round-end payout sheet (PR #152). Not a live game.
        </p>
      </header>

      <div className="flex flex-wrap gap-6">
        <div className="flex flex-col gap-2">
          <span className="text-xs uppercase tracking-wider text-white/50">Scenario</span>
          <div className="flex flex-wrap gap-2">
            {SCENARIO_KEYS.map((key) => (
              <button key={key} className={segButton(scenario === key)} onClick={() => setScenario(key)}>
                {SCENARIO_LABELS[key]}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-col gap-2">
          <span className="text-xs uppercase tracking-wider text-white/50">Viewport</span>
          <div className="flex flex-wrap gap-2">
            {VIEWPORTS.map((v) => (
              <button key={v.key} className={segButton(viewport === v.key)} onClick={() => setViewport(v.key)}>
                {v.label}
                <span className="ml-1 text-white/40">
                  {v.width}×{v.height}
                </span>
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-col gap-2">
          <span className="text-xs uppercase tracking-wider text-white/50">Ready badges</span>
          <button className={segButton(ready)} onClick={() => setReady((r) => !r)}>
            {ready ? 'On' : 'Off'}
          </button>
        </div>
      </div>

      <div className="flex justify-center overflow-auto rounded-xl bg-black/30 p-4">
        <iframe
          key={src}
          title="Round-result preview"
          src={src}
          style={{
            width: vp.width,
            height: vp.height,
            border: '1px solid rgba(255,255,255,0.15)',
            borderRadius: 12,
            background: '#071d1a',
            flex: '0 0 auto',
          }}
        />
      </div>
    </div>
  )
}

export default function RoundResultDemo() {
  const [params] = useSearchParams()
  return params.get('embed') === '1' ? <EmbeddedOverlay /> : <Playground />
}
