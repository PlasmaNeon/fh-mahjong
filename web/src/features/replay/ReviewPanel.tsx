import { useMemo } from 'react'
import type { ReportDecision, ReviewReport } from './reviewTypes'
import {
  SEVERITY_COLORS,
  SEVERITY_LABELS,
  actionLabel,
  buildDecisionIndex,
  decisionKey,
  decisionSeverity,
  resolveValuesCalibrated,
  selectBarRows,
  severityCounts,
  type SeverityThresholds,
} from './reviewUtils'

export type ReviewStatus = 'loading' | 'empty' | 'generating' | 'ready' | 'unavailable' | 'error'

export interface ReviewPanelProps {
  report: ReviewReport | null
  status: ReviewStatus
  errorMessage?: string | null
  onRequestReview: () => void
  viewSeat: number
  position: { round: number; actionIndex: number }
  onJump: (round: number, actionIndex: number) => void
  lang: 'en' | 'zh'
  onLangToggle: () => void
  thresholds: SeverityThresholds
  onThresholdsChange: (thresholds: SeverityThresholds) => void
}

/** Integrated post-game review overlay: decision bar chart, mistake summary, value sparkline. */
export default function ReviewPanel(props: ReviewPanelProps) {
  const {
    report, status, errorMessage, onRequestReview,
    viewSeat, position, onJump, lang, onLangToggle,
    thresholds, onThresholdsChange,
  } = props

  const decisionIndex = useMemo(
    () => (report ? buildDecisionIndex(report) : new Map<string, ReportDecision[]>()),
    [report],
  )

  const t = lang === 'zh'
    ? {
      title: '复盘',
      lang: 'EN',
      requestReview: '请求复盘',
      loading: '加载复盘中…',
      generating: '正在生成复盘…',
      unavailable: '复盘服务未配置',
      noDecision: '此位置无记录',
      analysis: '分析',
      mistakes: '失误摘要',
      topGaps: '主要差距',
      timeline: '价值趋势',
      thresholds: '阈值',
      disagreement: '分歧阈值',
      mistake: '失误阈值',
      caption: '冠军模型以冲刺名次为目标，仅供参考',
      decisions: '决策数',
      valuesUncalibrated: '该策略未提供价值估计',
    }
    : {
      title: 'Review',
      lang: '中',
      requestReview: 'Request review',
      loading: 'Loading review…',
      generating: 'Generating review…',
      unavailable: 'Reviewer unavailable — no policy server configured',
      noDecision: 'No decision recorded at this position',
      analysis: 'Analysis',
      mistakes: 'Mistake summary',
      topGaps: 'Top gaps',
      timeline: 'Value timeline',
      thresholds: 'Thresholds',
      disagreement: 'Disagreement',
      mistake: 'Mistake',
      caption: 'The champion optimizes final placement (Chongci) and is strong but not an oracle',
      decisions: 'decisions',
      valuesUncalibrated: 'Value estimates are unavailable for this policy',
    }

  return (
    <div className="review-panel">
      <div className="review-panel__head">
        <div className="review-panel__title">{t.title}</div>
        <button
          type="button"
          onClick={onLangToggle}
          className="review-panel__lang"
        >
          {t.lang}
        </button>
      </div>

      {!report ? (
        <ReviewRequestState
          status={status}
          errorMessage={errorMessage}
          onRequestReview={onRequestReview}
          t={t}
        />
      ) : (
        <ReviewContent
          report={report}
          decisionIndex={decisionIndex}
          viewSeat={viewSeat}
          position={position}
          onJump={onJump}
          lang={lang}
          thresholds={thresholds}
          onThresholdsChange={onThresholdsChange}
          t={t}
        />
      )}
    </div>
  )
}

interface CopyBundle {
  requestReview: string
  loading: string
  generating: string
  unavailable: string
  noDecision: string
  analysis: string
  mistakes: string
  topGaps: string
  timeline: string
  thresholds: string
  disagreement: string
  mistake: string
  caption: string
  decisions: string
  valuesUncalibrated: string
}

function ReviewRequestState({ status, errorMessage, onRequestReview, t }: {
  status: ReviewStatus
  errorMessage?: string | null
  onRequestReview: () => void
  t: CopyBundle
}) {
  if (status === 'loading') {
    return <div className="review-panel__muted">{t.loading}</div>
  }
  if (status === 'generating') {
    return <div className="review-panel__muted">{t.generating}</div>
  }
  return (
    <div className="review-panel__request">
      {status === 'unavailable' && (
        <div className="review-panel__warning">{t.unavailable}</div>
      )}
      {status === 'error' && errorMessage && (
        <div className="review-panel__error">{errorMessage}</div>
      )}
      <button type="button" onClick={onRequestReview} className="review-panel__button">
        {t.requestReview}
      </button>
    </div>
  )
}

function ReviewContent({ report, decisionIndex, viewSeat, position, onJump, lang, thresholds, onThresholdsChange, t }: {
  report: ReviewReport
  decisionIndex: Map<string, ReportDecision[]>
  viewSeat: number
  position: { round: number; actionIndex: number }
  onJump: (round: number, actionIndex: number) => void
  lang: 'en' | 'zh'
  thresholds: SeverityThresholds
  onThresholdsChange: (thresholds: SeverityThresholds) => void
  t: CopyBundle
}) {
  const key = decisionKey(position.round, position.actionIndex)
  const decisionsAtKey = decisionIndex.get(key) ?? []
  const current = decisionsAtKey.find(d => d.seat === viewSeat) ?? null

  const seatDecisions = useMemo(
    () => report.decisions
      .filter(d => d.seat === viewSeat)
      .sort((a, b) => (a.round - b.round) || (a.actionIndex - b.actionIndex)),
    [report, viewSeat],
  )
  const seatSummary = report.seats.find(s => s.seat === viewSeat) ?? null
  const counts = severityCounts(seatDecisions, thresholds)

  return (
    <div className="review-panel__content">
      <DecisionAnalysis decision={current} lang={lang} thresholds={thresholds} noDecisionLabel={t.noDecision} analysisLabel={t.analysis} />

      <div>
        <div className="review-panel__heading">{t.mistakes}</div>
        <div className="review-panel__severity-row">
          <SeverityCount label={SEVERITY_LABELS.ok[lang]} color={SEVERITY_COLORS.ok} count={counts.ok} />
          <SeverityCount label={SEVERITY_LABELS.disagreement[lang]} color={SEVERITY_COLORS.disagreement} count={counts.disagreement} />
          <SeverityCount label={SEVERITY_LABELS.mistake[lang]} color={SEVERITY_COLORS.mistake} count={counts.mistake} />
        </div>
        {seatSummary && seatSummary.topGaps.length > 0 && (
          <div className="review-panel__gap-list">
            <div className="review-panel__micro">{t.topGaps}</div>
            {seatSummary.topGaps.map((g, i) => {
              const d = report.decisions[g.decision]
              if (!d) return null
              return (
                <button
                  key={i}
                  type="button"
                  onClick={() => onJump(d.round, d.actionIndex)}
                  className="review-panel__gap-button"
                >
                  R{d.round + 1} · {actionLabel(d.chosenActionId)[lang]} · gap {g.gap.toFixed(2)}
                </button>
              )
            })}
          </div>
        )}
      </div>

      <ValueSparkline
        decisions={seatDecisions}
        position={position}
        onJump={onJump}
        label={t.timeline}
        valuesCalibrated={resolveValuesCalibrated(report)}
        uncalibratedLabel={t.valuesUncalibrated}
      />

      <details className="review-panel__advanced">
        <summary>{t.thresholds}</summary>
        <ThresholdControls thresholds={thresholds} onThresholdsChange={onThresholdsChange} t={t} />
      </details>

      <div className="review-panel__caption">
        {t.caption}
      </div>
    </div>
  )
}

function SeverityCount({ label, color, count }: { label: string; color: string; count: number }) {
  return (
    <div className="review-severity">
      <span className="review-severity__dot" style={{ background: color }} />
      <span className="review-severity__count">{count}</span>
      <span className="review-severity__label">{label}</span>
    </div>
  )
}

function DecisionAnalysis({ decision, lang, thresholds, noDecisionLabel, analysisLabel }: {
  decision: ReportDecision | null
  lang: 'en' | 'zh'
  thresholds: SeverityThresholds
  noDecisionLabel: string
  analysisLabel: string
}) {
  if (!decision) {
    return (
      <div>
        <div className="review-panel__heading">{analysisLabel}</div>
        <div className="review-panel__muted">{noDecisionLabel}</div>
      </div>
    )
  }

  const severity = decisionSeverity(decision, thresholds)
  const rows = selectBarRows(decision)
  const top = decision.actions[0]
  const preferText = top && top.actionId !== decision.chosenActionId
    ? (lang === 'zh'
      ? `冠军模型倾向 ${actionLabel(top.actionId).zh} (${Math.round(top.prob * 100)}%)`
      : `Champion prefers ${actionLabel(top.actionId).en} (${Math.round(top.prob * 100)}%)`)
    : null

  return (
    <div>
      <div className="review-analysis__head">
        <div className="review-panel__heading">{analysisLabel}</div>
        <span className="review-analysis__badge" style={{ background: SEVERITY_COLORS[severity] }}>
          {SEVERITY_LABELS[severity][lang]}
        </span>
      </div>
      <div className="review-analysis__bars">
        {rows.map(row => {
          const label = actionLabel(row.actionId)[lang]
          const pct = Math.round(row.prob * 100)
          const barColor = row.isChosen ? SEVERITY_COLORS[severity] : 'rgba(255,255,255,0.25)'
          return (
            <div key={row.actionId} className="review-analysis__row">
              <span className={`review-analysis__label${row.isChosen ? ' is-chosen' : ''}`}>
                {label}
              </span>
              <div className="review-analysis__track">
                <div style={{
                  width: `${Math.max(pct, row.prob > 0 ? 2 : 0)}%`,
                  background: barColor,
                }} className={`review-analysis__fill${row.isChosen ? ' is-chosen' : ''}`} />
              </div>
              <span className="review-analysis__percent">{pct}%</span>
            </div>
          )
        })}
      </div>
      {preferText && (
        <div className="review-analysis__preference">{preferText}</div>
      )}
    </div>
  )
}

function ValueSparkline({ decisions, position, onJump, label, valuesCalibrated, uncalibratedLabel }: {
  decisions: ReportDecision[]
  position: { round: number; actionIndex: number }
  onJump: (round: number, actionIndex: number) => void
  label: string
  valuesCalibrated: boolean
  uncalibratedLabel: string
}) {
  if (decisions.length === 0) {
    return null
  }
  if (!valuesCalibrated) {
    return (
      <div>
        <div className="review-panel__heading">{label}</div>
        <div className="review-panel__warning">{uncalibratedLabel}</div>
      </div>
    )
  }

  // Values are non-null whenever valuesCalibrated is true (see
  // ReviewReport.valuesCalibrated), but guard defensively against a
  // partially-populated report.
  const withValue = decisions.filter((d): d is ReportDecision & { value: number } => d.value != null)
  if (withValue.length === 0) {
    return null
  }

  const width = 248
  const height = 40
  const values = withValue.map(d => d.value)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1

  const points = withValue.map((d, i) => {
    const x = withValue.length > 1 ? (i / (withValue.length - 1)) * width : width / 2
    const y = height - ((d.value - min) / span) * height
    return { x, y, d }
  })

  const path = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
  const currentKey = decisionKey(position.round, position.actionIndex)

  return (
    <div>
      <div className="review-panel__heading">{label}</div>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="review-sparkline">
        <path d={path} fill="none" stroke="var(--brass)" strokeWidth={1.5} />
        {points.map((p, i) => {
          const isCurrent = decisionKey(p.d.round, p.d.actionIndex) === currentKey
          return (
            <circle
              key={i}
              cx={p.x}
              cy={p.y}
              r={isCurrent ? 3.5 : 2}
              fill={isCurrent ? 'var(--brass-light)' : 'rgba(210, 168, 95, 0.58)'}
              stroke={isCurrent ? 'var(--on-dark)' : 'none'}
              strokeWidth={1}
              style={{ cursor: 'pointer' }}
              onClick={() => onJump(p.d.round, p.d.actionIndex)}
            />
          )
        })}
      </svg>
    </div>
  )
}

function ThresholdControls({ thresholds, onThresholdsChange, t }: {
  thresholds: SeverityThresholds
  onThresholdsChange: (thresholds: SeverityThresholds) => void
  t: CopyBundle
}) {
  return (
    <div>
      <div className="review-panel__heading">{t.thresholds}</div>
      <SliderRow
        label={t.disagreement}
        value={thresholds.disagreement}
        onChange={v => onThresholdsChange({ ...thresholds, disagreement: v })}
      />
      <SliderRow
        label={t.mistake}
        value={thresholds.mistake}
        onChange={v => onThresholdsChange({ ...thresholds, mistake: v })}
      />
    </div>
  )
}

function SliderRow({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  return (
    <div className="review-slider">
      <span className="review-slider__label">{label}</span>
      <input
        type="range"
        min={0}
        max={1}
        step={0.01}
        value={value}
        onChange={e => onChange(Number(e.target.value))}
        className="review-slider__input"
      />
      <span className="review-slider__value">{value.toFixed(2)}</span>
    </div>
  )
}
