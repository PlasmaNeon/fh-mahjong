import { useMemo } from 'react'
import type { ReportDecision, ReviewReport } from './reviewTypes'
import {
  SEVERITY_COLORS,
  SEVERITY_LABELS,
  actionLabel,
  buildDecisionIndex,
  decisionKey,
  decisionSeverity,
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

const panelSectionStyle: React.CSSProperties = {
  borderTop: '1px solid rgba(255,255,255,0.1)',
  paddingTop: '12px',
  marginTop: '4px',
}

const headingStyle: React.CSSProperties = {
  fontSize: '12px',
  color: '#9ca3af',
  marginBottom: '6px',
  textTransform: 'uppercase',
  letterSpacing: '0.03em',
}

const buttonStyle: React.CSSProperties = {
  padding: '8px 12px',
  background: 'rgba(16, 185, 129, 0.25)',
  border: '1px solid #10b981',
  borderRadius: '6px',
  color: '#e5e7eb',
  cursor: 'pointer',
  fontSize: '13px',
  fontWeight: 600,
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
    }

  return (
    <div style={panelSectionStyle}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
        <div style={{ fontSize: '14px', fontWeight: 700 }}>{t.title}</div>
        <button
          type="button"
          onClick={onLangToggle}
          style={{
            padding: '2px 8px',
            background: 'rgba(255,255,255,0.08)',
            border: '1px solid rgba(255,255,255,0.15)',
            borderRadius: '4px',
            color: '#9ca3af',
            cursor: 'pointer',
            fontSize: '11px',
          }}
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
}

function ReviewRequestState({ status, errorMessage, onRequestReview, t }: {
  status: ReviewStatus
  errorMessage?: string | null
  onRequestReview: () => void
  t: CopyBundle
}) {
  if (status === 'loading') {
    return <div style={{ fontSize: '13px', color: '#9ca3af' }}>{t.loading}</div>
  }
  if (status === 'generating') {
    return <div style={{ fontSize: '13px', color: '#9ca3af' }}>{t.generating}</div>
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      {status === 'unavailable' && (
        <div style={{ fontSize: '12px', color: '#f59e0b' }}>{t.unavailable}</div>
      )}
      {status === 'error' && errorMessage && (
        <div style={{ fontSize: '12px', color: '#ef4444' }}>{errorMessage}</div>
      )}
      <button type="button" onClick={onRequestReview} style={buttonStyle}>
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
    <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
      <DecisionAnalysis decision={current} lang={lang} thresholds={thresholds} noDecisionLabel={t.noDecision} analysisLabel={t.analysis} />

      <div>
        <div style={headingStyle}>{t.mistakes}</div>
        <div style={{ display: 'flex', gap: '10px', fontSize: '12px', marginBottom: '6px' }}>
          <SeverityCount label={SEVERITY_LABELS.ok[lang]} color={SEVERITY_COLORS.ok} count={counts.ok} />
          <SeverityCount label={SEVERITY_LABELS.disagreement[lang]} color={SEVERITY_COLORS.disagreement} count={counts.disagreement} />
          <SeverityCount label={SEVERITY_LABELS.mistake[lang]} color={SEVERITY_COLORS.mistake} count={counts.mistake} />
        </div>
        {seatSummary && seatSummary.topGaps.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <div style={{ fontSize: '11px', color: '#6b7280' }}>{t.topGaps}</div>
            {seatSummary.topGaps.map((g, i) => {
              const d = report.decisions[g.decision]
              if (!d) return null
              return (
                <button
                  key={i}
                  type="button"
                  onClick={() => onJump(d.round, d.actionIndex)}
                  style={{
                    textAlign: 'left',
                    background: 'rgba(255,255,255,0.05)',
                    border: '1px solid rgba(255,255,255,0.1)',
                    borderRadius: '4px',
                    padding: '4px 8px',
                    color: '#e5e7eb',
                    cursor: 'pointer',
                    fontSize: '12px',
                  }}
                >
                  R{d.round + 1} · {actionLabel(d.chosenActionId)[lang]} · gap {g.gap.toFixed(2)}
                </button>
              )
            })}
          </div>
        )}
      </div>

      <ValueSparkline decisions={seatDecisions} position={position} onJump={onJump} label={t.timeline} />

      <ThresholdControls thresholds={thresholds} onThresholdsChange={onThresholdsChange} t={t} />

      <div style={{ fontSize: '11px', color: '#6b7280', fontStyle: 'italic', lineHeight: 1.4 }}>
        {t.caption}
      </div>
    </div>
  )
}

function SeverityCount({ label, color, count }: { label: string; color: string; count: number }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
      <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: color, display: 'inline-block' }} />
      <span style={{ color: '#e5e7eb' }}>{count}</span>
      <span style={{ color: '#6b7280' }}>{label}</span>
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
        <div style={headingStyle}>{analysisLabel}</div>
        <div style={{ fontSize: '12px', color: '#6b7280' }}>{noDecisionLabel}</div>
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
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
        <div style={headingStyle}>{analysisLabel}</div>
        <span style={{
          fontSize: '11px',
          fontWeight: 700,
          padding: '2px 8px',
          borderRadius: '10px',
          color: '#111827',
          background: SEVERITY_COLORS[severity],
        }}>
          {SEVERITY_LABELS[severity][lang]}
        </span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
        {rows.map(row => {
          const label = actionLabel(row.actionId)[lang]
          const pct = Math.round(row.prob * 100)
          const barColor = row.isChosen ? SEVERITY_COLORS[severity] : 'rgba(255,255,255,0.25)'
          return (
            <div key={row.actionId} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px' }}>
              <span style={{
                flex: '0 0 92px',
                color: row.isChosen ? '#e5e7eb' : '#9ca3af',
                fontWeight: row.isChosen ? 700 : 400,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}>
                {label}
              </span>
              <div style={{ flex: 1, height: '10px', background: 'rgba(255,255,255,0.08)', borderRadius: '3px', overflow: 'hidden' }}>
                <div style={{
                  width: `${Math.max(pct, row.prob > 0 ? 2 : 0)}%`,
                  height: '100%',
                  background: barColor,
                  border: row.isChosen ? '1px solid rgba(255,255,255,0.5)' : 'none',
                }} />
              </div>
              <span style={{ flex: '0 0 32px', textAlign: 'right', color: '#9ca3af' }}>{pct}%</span>
            </div>
          )
        })}
      </div>
      {preferText && (
        <div style={{ fontSize: '11px', color: '#9ca3af', marginTop: '6px' }}>{preferText}</div>
      )}
    </div>
  )
}

function ValueSparkline({ decisions, position, onJump, label }: {
  decisions: ReportDecision[]
  position: { round: number; actionIndex: number }
  onJump: (round: number, actionIndex: number) => void
  label: string
}) {
  if (decisions.length === 0) {
    return null
  }
  const width = 248
  const height = 40
  const values = decisions.map(d => d.value)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1

  const points = decisions.map((d, i) => {
    const x = decisions.length > 1 ? (i / (decisions.length - 1)) * width : width / 2
    const y = height - ((d.value - min) / span) * height
    return { x, y, d }
  })

  const path = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
  const currentKey = decisionKey(position.round, position.actionIndex)

  return (
    <div>
      <div style={headingStyle}>{label}</div>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} style={{ display: 'block' }}>
        <path d={path} fill="none" stroke="#10b981" strokeWidth={1.5} />
        {points.map((p, i) => {
          const isCurrent = decisionKey(p.d.round, p.d.actionIndex) === currentKey
          return (
            <circle
              key={i}
              cx={p.x}
              cy={p.y}
              r={isCurrent ? 3.5 : 2}
              fill={isCurrent ? '#34d399' : 'rgba(16, 185, 129, 0.6)'}
              stroke={isCurrent ? '#ffffff' : 'none'}
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
      <div style={headingStyle}>{t.thresholds}</div>
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
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '11px', marginBottom: '4px' }}>
      <span style={{ flex: '0 0 84px', color: '#9ca3af' }}>{label}</span>
      <input
        type="range"
        min={0}
        max={1}
        step={0.01}
        value={value}
        onChange={e => onChange(Number(e.target.value))}
        style={{ flex: 1, accentColor: '#10b981' }}
      />
      <span style={{ flex: '0 0 32px', textAlign: 'right', color: '#e5e7eb' }}>{value.toFixed(2)}</span>
    </div>
  )
}

