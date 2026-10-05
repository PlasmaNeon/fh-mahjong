import { useEffect, useRef, useState } from 'react'
import { useI18n } from '../../i18n/I18nContext'
import { reviewPatternKey } from '../../i18n/locales/review'
import type { Paipu } from './replayTypes'
import type { ReportDecision, ReviewReport } from './reviewClient'
import type { StudyJob } from './studyClient'
import {
  actualKnown,
  agreementStats,
  bestAction,
  cumulativeProxy,
  discardRiskLog,
  drawLog,
  riskForAction,
  errorRatio,
  faceLabel,
  isStudyError,
  studyActionLabel,
} from './studyUtils'
import { decisionGap, decisionSeverity, SEVERITY_THRESHOLDS, type SeverityThresholds } from './reviewUtils'
export type StudySettings = {
  advice: boolean
  relative: boolean
  study: boolean
  revealed: boolean
  risk: boolean
  wheel: boolean
  help: boolean
  logs: boolean
  details: boolean
  evaluationSort: 'confidence' | 'value'
  threshold: number
  tab: 'decision' | 'rounds' | 'risk'
}
export const defaultStudySettings: StudySettings = {
  advice: true,
  relative: false,
  study: false,
  revealed: false,
  risk: false,
  wheel: false,
  help: false,
  logs: false,
  details: true,
  evaluationSort: 'confidence',
  threshold: 100,
  tab: 'decision',
}
export function studyHidden(settings: StudySettings) {
  return settings.study && !settings.revealed
}
const percent = (p: number | null | undefined) => (p == null ? '—' : `${(100 * p).toFixed(1)}%`)
type Props = {
  paipu: Paipu
  report: ReviewReport | null
  decision?: ReportDecision
  seat: number
  round: number
  cursor: number
  job: StudyJob | null
  error: string
  running: boolean
  authenticated: boolean
  run: () => void
  cancel: () => void
  jump: (d: ReportDecision) => void
  jumpRound: (r: number, end?: boolean) => void
  navigate: (delta: number, errors?: boolean) => void
  settings: StudySettings
  change: (change: Partial<StudySettings>) => void
  bookmark: () => void
  copied: boolean
  thresholds: SeverityThresholds
  onThresholds: (t: SeverityThresholds) => void
}
export default function ReviewStudy({
  paipu,
  report,
  decision,
  seat,
  round: currentRound,
  cursor,
  job,
  error,
  running,
  authenticated,
  run,
  cancel,
  jump,
  jumpRound,
  navigate,
  settings,
  change,
  bookmark,
  copied,
  thresholds,
  onThresholds,
}: Props) {
  const { t, language, setLanguage } = useI18n()
  const [riskSelection, setRiskSelection] = useState<{
    id?: string
    face: number
  } | null>(null)
  const selectedRisk =
    riskSelection?.id === decision?.id
      ? decision?.risk?.tiles.find((tile) => tile.face === riskSelection?.face)
      : undefined
  const riskDialog = useRef<HTMLDialogElement>(null)
  const riskVisible = !!selectedRisk
  useEffect(() => {
    if (!riskVisible || !riskDialog.current) return
    const previousFocus = document.activeElement
    const dialog = riskDialog.current
    dialog.showModal()
    return () => {
      dialog.close()
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus()
    }
  }, [riskVisible, riskSelection?.id, riskSelection?.face])
  const hidden = studyHidden(settings)
  const advice = !hidden && settings.advice
  const decisions =
    report?.decisions.filter(
      (d) =>
        d.seat === seat &&
        (!settings.study ||
          d.round < currentRound ||
          (d.round === currentRound && (d.positionIndex ?? d.actionIndex - 1) <= cursor)),
    ) ?? []
  const stats = agreementStats(decisions)
  const best = decision ? bestAction(decision) : undefined
  const label = (id: number) => studyActionLabel(id, t)
  const rank = decision?.actions.findIndex((a) => a.actionId === decision.chosenActionId)
  const riskLog = discardRiskLog(decisions),
    draws = drawLog(decisions)
  const button = (text: string, action: () => void, disabled = false) => (
    <button type="button" className="replay-choice" onClick={action} disabled={disabled}>
      {text}
    </button>
  )
  const check = (field: 'advice' | 'relative' | 'study' | 'risk' | 'wheel', text: string) => (
    <label className="replay-check">
      <input
        type="checkbox"
        checked={settings[field]}
        onChange={(event) =>
          change({
            [field]: event.target.checked,
            ...(field === 'study' ? { revealed: false } : {}),
          })
        }
      />
      {text}
    </label>
  )
  return (
    <section className="review-panel review-study">
      <div className="review-panel__head">
        <strong className="review-panel__title">{t('review.title')}</strong>
        <select
          aria-label={t('review.help')}
          className="review-language"
          value={language}
          onChange={(e) => setLanguage(e.target.value as typeof language)}
        >
          {[
            ['en', 'English'],
            ['zh-CN', '简体中文'],
            ['ja', '日本語'],
            ['ko', '한국어'],
            ['ru', 'Русский'],
          ].map(([value, name]) => (
            <option key={value} value={value}>
              {name}
            </option>
          ))}
        </select>
      </div>
      {!authenticated ? (
        <a
          href={`/login?returnTo=${encodeURIComponent(typeof location === 'undefined' ? '/replay' : location.pathname + location.search)}`}
        >
          {t('review.signIn')}
        </a>
      ) : (
        <div className="replay-choice-row">
          {button(job ? t('review.retry') : t('review.analyze'), run, running || job?.state === 'complete')}
          {running && button(t('review.cancel'), cancel)}
        </div>
      )}
      {job && (
        <div role="status" className="review-panel__muted">
          {t('review.progress', {
            state: t(`review.state${job.state}` as Parameters<typeof t>[0]),
            done: job.completed,
            total: job.total,
          })}
          <progress max={Math.max(1, job.total)} value={job.completed} aria-label={t('review.title')} />
        </div>
      )}
      {(error || job?.error) && (
        <p role="alert" className="review-panel__error">
          {error || job?.error}
        </p>
      )}
      {!report && <p className="review-panel__muted">{t('review.empty')}</p>}
      {report?.study && !report.study.complete && <p className="review-panel__warning">{t('review.partial')}</p>}
      <div className="review-settings">
        {check('study', t('review.study'))}
        {settings.study && button(t('review.reveal'), () => change({ revealed: !settings.revealed }))}
        {check('advice', t('review.advice'))}
        {check('relative', t('review.relative'))}
        {check('risk', t('review.risk'))}
        {check('wheel', t('review.wheel'))}
      </div>
      <div className="replay-choice-row">
        {button('‹ ' + t('review.previous'), () => navigate(-1))}
        {button(t('review.next') + ' ›', () => navigate(1))}
        {button('‹ ' + t('review.previousError'), () => navigate(-1, true), hidden)}
        {button(t('review.nextError') + ' ›', () => navigate(1, true), hidden)}
      </div>
      {!hidden && (
        <label className="review-threshold">
          {t('review.ratio')}
          <input
            type="number"
            min={0}
            max={100}
            value={settings.threshold}
            onChange={(e) =>
              change({
                threshold: Math.max(0, Math.min(100, Number(e.target.value))),
              })
            }
          />
        </label>
      )}
      <div className="review-tabs" role="tablist" aria-label={t('review.title')}>
        {(['decision', 'rounds', 'risk'] as const).map((tab) => (
          <button
            role="tab"
            aria-selected={settings.tab === tab}
            key={tab}
            className={`replay-choice ${settings.tab === tab ? 'is-active' : ''}`}
            onClick={() => change({ tab })}
          >
            {t(`review.${tab}`)}
          </button>
        ))}
      </div>
      {settings.tab === 'decision' && (
        <div className="review-panel__content" role="tabpanel">
          {!decision ? (
            <p className="review-panel__muted">{t('review.noDecision')}</p>
          ) : (
            <>
              <div className="review-panel__heading">
                {t('review.atDecision', {
                  round: decision.round + 1,
                  id: decision.id ?? decision.actionIndex,
                })}
              </div>
              {advice && (
                <>
                  {!actualKnown(decision) ? (
                    <p className="review-panel__warning">{t('review.inferred')}</p>
                  ) : (
                    <div className="review-comparison">
                      <div>
                        <span>{t('review.actual')}</span>
                        <strong>{label(decision.chosenActionId)}</strong>
                        <small>{percent(decision.chosenProb)}</small>
                      </div>
                      <div>
                        <span>{t('review.best')}</span>
                        <strong>{best ? label(best.actionId) : '—'}</strong>
                        <small>{percent(best?.prob)}</small>
                      </div>
                    </div>
                  )}
                  {actualKnown(decision) && (
                    <div className="review-panel__muted">
                      {t('review.ranking', {
                        rank: (rank ?? -1) + 1,
                        gap: percent(decisionGap(decision)),
                      })}{' '}
                      · {errorRatio(decision).toFixed(1)}% · {decisionSeverity(decision, thresholds)}
                    </div>
                  )}
                  <div className="review-operation-bars">
                    {decision.actions.map((a) => (
                      <div key={a.actionId} className="review-operation">
                        <span>
                          {label(a.actionId)}
                          {actualKnown(decision) && a.actionId === decision.chosenActionId ? ' ●' : ''}
                          {a.actionId === best?.actionId ? ' ★' : ''}
                        </span>
                        <div className="review-operation__track">
                          <i
                            style={{
                              width: `${100 * (settings.relative && best?.prob ? a.prob / best.prob : a.prob)}%`,
                            }}
                          />
                        </div>
                        <small>{percent(a.prob)}</small>
                      </div>
                    ))}
                  </div>
                  {button(t('review.evaluation'), () => change({ details: !settings.details }))}
                  {settings.details && (
                    <>
                      <div className="review-scroll">
                        <table className="study-table">
                          <thead>
                            <tr>
                              <th>{t('review.decision')}</th>
                              <th>
                                <button
                                  className="replay-choice"
                                  aria-pressed={settings.evaluationSort === 'confidence'}
                                  onClick={() => change({ evaluationSort: 'confidence' })}
                                >
                                  {t('review.probability')}
                                </button>
                              </th>
                              <th>
                                <button
                                  className="replay-choice"
                                  aria-pressed={settings.evaluationSort === 'value'}
                                  onClick={() => change({ evaluationSort: 'value' })}
                                >
                                  {t('review.evaluation')}
                                </button>
                              </th>
                            </tr>
                          </thead>
                          <tbody>
                            {[...decision.actions]
                              .sort(
                                (a, b) =>
                                  (settings.evaluationSort === 'value'
                                    ? (b.evaluation?.mean ?? -Infinity) - (a.evaluation?.mean ?? -Infinity)
                                    : 0) || b.prob - a.prob,
                              )
                              .map((a) => (
                                <tr
                                  key={a.actionId}
                                  data-chosen={
                                    (actualKnown(decision) && a.actionId === decision.chosenActionId) || undefined
                                  }
                                >
                                  <td>{label(a.actionId)}</td>
                                  <td>{percent(a.prob)}</td>
                                  <td>
                                    {a.evaluation ? (
                                      <>
                                        {a.evaluation.mean.toFixed(1)} ± {a.evaluation.standardError.toFixed(1)}
                                        <small>n={a.evaluation.samples}</small>
                                      </>
                                    ) : (
                                      t('review.pending')
                                    )}
                                  </td>
                                </tr>
                              ))}
                          </tbody>
                        </table>
                      </div>
                      <p className="review-panel__caption">{t('review.evaluationHelp')}</p>
                    </>
                  )}
                </>
              )}
            </>
          )}
          {!hidden && (
            <>
              <div className="review-metrics">
                <span>
                  {t('review.agreement')}
                  <strong>{percent(stats.agreement)}</strong>
                  <small>n={stats.count}</small>
                </span>
                <span>
                  {t('review.rating')}
                  <strong>{stats.rating?.toFixed(1) ?? '—'} / 100</strong>
                  <small>n={stats.ratingCount}</small>
                </span>
              </div>
              <div className="review-decision-list">
                {decisions
                  .filter((d) => isStudyError(d, settings.threshold))
                  .map((d) => (
                    <button key={d.id} className="review-panel__gap-button" onClick={() => jump(d)}>
                      R{d.round + 1} · {label(d.chosenActionId)} · {errorRatio(d).toFixed(1)}%
                    </button>
                  ))}
              </div>
            </>
          )}
        </div>
      )}
      {settings.tab === 'rounds' && (
        <div role="tabpanel">
          <div className="review-scroll">
            <table className="study-table">
              <thead>
                <tr>
                  <th>{t('replay.round')}</th>
                  {paipu.players.map((p) => (
                    <th key={p.seat}>{p.name}</th>
                  ))}
                  <th>{t('review.agreement')}</th>
                  <th>{t('review.rating')}</th>
                  <th>{t('review.result')}</th>
                </tr>
              </thead>
              <tbody>
                {paipu.rounds.map((round, index) => (
                  <tr key={index}>
                    <td>
                      {button(String(index + 1), () => jumpRound(index))}
                      {button('↦', () => jumpRound(index, true))}
                    </td>
                    {round.startingScores.map((score, s) => (
                      <td key={s}>
                        {!settings.study || index <= currentRound ? score : '—'}
                        {!settings.study && (
                          <small>
                            {(round.result?.scoreChanges[s] ?? 0) >= 0 ? '+' : ''}
                            {round.result?.scoreChanges[s] ?? '—'}
                          </small>
                        )}
                      </td>
                    ))}
                    <td>
                      {hidden ? '-' : percent(agreementStats(decisions.filter((d) => d.round === index)).agreement)}
                      <small>
                        n=
                        {hidden ? '-' : agreementStats(decisions.filter((d) => d.round === index)).count}
                      </small>
                    </td>
                    <td>
                      {hidden
                        ? '—'
                        : (agreementStats(decisions.filter((d) => d.round === index)).rating?.toFixed(1) ?? '—')}
                      <small>
                        n={hidden ? '—' : agreementStats(decisions.filter((d) => d.round === index)).ratingCount}
                      </small>
                    </td>
                    <td>
                      {!settings.study && round.result
                        ? round.result.type === 'draw'
                          ? t('result.draw')
                          : `${t(round.result.winType === 'ron' ? 'review.ron' : 'review.tsumo')} · ${paipu.players[round.result.winner ?? 0]?.name}`
                        : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!settings.study && (
            <>
              <h4>{t('review.final')}</h4>
              {paipu.players
                .map((p) => ({ ...p, score: paipu.finalScores[p.seat] }))
                .sort((a, b) => b.score - a.score)
                .map((p) => (
                  <div key={p.seat} className="replay-score">
                    {1 + paipu.finalScores.filter((score) => score > p.score).length}. {p.name}
                    <strong>{p.score}</strong>
                  </div>
                ))}
            </>
          )}
        </div>
      )}
      {settings.tab === 'risk' && (
        <div role="tabpanel">
          <p className="review-panel__caption">{t('review.riskHelp')}</p>
          <details>
            <summary>{t('review.visibility')}</summary>
            <p>{t('review.visibilityHelp')}</p>
          </details>
          {hidden ? (
            <p>{t('review.study')}</p>
          ) : (
            <>
              {decision?.risk && (
                <>
                  <div className="review-scroll">
                    <table className="study-table">
                      <thead>
                        <tr>
                          <th>{t('review.decision')}</th>
                          <th>{t('review.unseen')}</th>
                          <th>{t('review.joint')}</th>
                          {decision.risk.tiles[0]?.opponents.map((o) => (
                            <th key={o.seat}>{paipu.players[o.seat]?.name}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {decision.risk.tiles.map((tile) => (
                          <tr key={tile.face}>
                            <td>
                              <button
                                className="replay-choice"
                                onClick={() =>
                                  setRiskSelection({
                                    id: decision.id,
                                    face: tile.face,
                                  })
                                }
                              >
                                {faceLabel(tile.face)}
                                {tile.inHand ? ' ●' : ''}
                              </button>
                            </td>
                            <td>{tile.unseen}</td>
                            <td>{percent(tile.anyRon)}</td>
                            {tile.opponents.map((o) => (
                              <td key={o.seat}>{percent(o.ron)}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <small>n={decision.risk.samples}</small>
                  {decision.risk.operations.map((o) => (
                    <p key={o.actionId}>
                      {label(o.actionId)} · {percent(o.anyRon)}
                    </p>
                  ))}
                </>
              )}
              {selectedRisk && (
                <dialog
                  ref={riskDialog}
                  className="review-risk-detail"
                  aria-label={t('review.contributors')}
                  onCancel={() => setRiskSelection(null)}
                >
                  <div className="review-panel__head">
                    <strong>
                      {faceLabel(selectedRisk.face)} · {t('review.contributors')}
                    </strong>
                    <button
                      type="button"
                      className="replay-choice"
                      autoFocus
                      aria-label={t('review.close')}
                      onClick={() => setRiskSelection(null)}
                    >
                      ×
                    </button>
                  </div>
                  {selectedRisk.opponents.map((o) => (
                    <div key={o.seat}>
                      <strong>
                        {paipu.players[o.seat]?.name} · {percent(o.ron)}
                      </strong>
                      {o.contributors.map((c) => (
                        <details key={c.patternId}>
                          <summary>
                            {reviewPatternKey(c.patternId) ? t(reviewPatternKey(c.patternId)!) : c.patternName} · {percent(c.frequency)}
                          </summary>
                          <p>
                            {t('review.example')}: {c.exampleFaces.map(faceLabel).join(' ')}
                          </p>
                        </details>
                      ))}
                    </div>
                  ))}
                </dialog>
              )}
            </>
          )}
        </div>
      )}
      {!hidden && button(t('review.riskLog') + ' / ' + t('review.drawLog'), () => change({ logs: !settings.logs }))}
      {!hidden && settings.logs && (
        <div className="review-logs">
          <h4>{t('review.riskLog')}</h4>
          <p>
            {t('review.proxy')}: {percent(cumulativeProxy(riskLog.map((row) => row.probability)))}
          </p>
          {riskLog.map((row, index) => (
            <div key={row.decision.id}>
              <button className="review-panel__gap-button" onClick={() => jump(row.decision)}>
                R{row.decision.round + 1} · {label(row.decision.chosenActionId)} · {percent(row.probability)} · Σ{' '}
                {percent(cumulativeProxy(riskLog.slice(0, index + 1).map((r) => r.probability)))}
              </button>
              {riskForAction(row.decision)?.opponents.map((opponent) => (
                <small className="review-log-opponent" key={opponent.seat}>
                  {paipu.players[opponent.seat]?.name}: {percent(opponent.ron)} · Σ{' '}
                  {percent(
                    cumulativeProxy(
                      riskLog
                        .slice(0, index + 1)
                        .map(
                          (r) => riskForAction(r.decision)?.opponents.find((o) => o.seat === opponent.seat)?.ron ?? 0,
                        ),
                    ),
                  )}
                </small>
              ))}
              {(!settings.study || row.decision.round < currentRound || row.decision.actionIndex + 1 <= cursor) && (
                <small className="review-log-opponent">
                  {t('review.result')}:{' '}
                  {t(
                    paipu.rounds[row.decision.round].actions[row.decision.actionIndex + 1]?.act === 'ron'
                      ? 'review.ron'
                      : 'review.miss',
                  )}
                </small>
              )}
            </div>
          ))}
          <h4>{t('review.drawLog')}</h4>
          <p>
            {draws.filter((d) => d.draw!.hit).length}/{draws.length} · {t('review.proxy')}:{' '}
            {percent(cumulativeProxy(draws.map((d) => d.draw!.chance)))}
          </p>
          {draws.map((d, index) => (
            <details key={d.id}>
              <summary>
                <button className="review-panel__gap-button" onClick={() => jump(d)}>
                  R{d.round + 1} · {t(d.draw!.hit ? 'review.hit' : 'review.miss')} · {percent(d.draw!.chance)} · Σ{' '}
                  {percent(cumulativeProxy(draws.slice(0, index + 1).map((row) => row.draw!.chance)))}
                </button>
              </summary>
              {t('review.unseen')}: {d.draw!.unseen}
              <p>{d.draw!.waits.map((w) => `${faceLabel(w.face)} ×${w.remaining} (${w.points})`).join(' · ') || '—'}</p>
              <small>{d.draw!.source}</small>
            </details>
          ))}
          <p className="review-panel__caption">{t('review.proxyHelp')}</p>
        </div>
      )}
      <div className="replay-choice-row">
        {button(t(copied ? 'review.copied' : 'review.bookmark'), bookmark)}
        {button(t('review.help'), () => change({ help: !settings.help }))}
      </div>
      {settings.help && (
        <div className="review-help">
          <p>{t('review.keys')}</p>
          <h4>{t('review.metadata')}</h4>
          {report && (
            <dl>
              <dt>
                {paipu.ruleset} · schema {report.schemaVersion} · paipu v{paipu.version}
              </dt>
              <dd>
                {paipu.matchMode ?? 'classic'} · {paipu.rounds.length} {t('review.rounds')} · {report.decisions.length}{' '}
                {t('review.decision')}
              </dd>
              <dt>{report.checkpointPath.split('/').pop()}</dt>
              <dd>{report.checkpointSha256}</dd>
              <dt>{new Date(report.generatedAt).toLocaleString(language)}</dt>
              <dd>
                {report.study?.method} · event window {report.study?.eventWindow} ·{' '}
                {((report.study?.buildMillis ?? 0) / 1000).toFixed(1)}s
              </dd>
              <dt>{report.study?.units}</dt>
              <dd>{JSON.stringify(report.study?.config)}</dd>
            </dl>
          )}
          <details>
            <summary>{t('review.ratio')}</summary>
            {Object.entries(thresholds).map(([key, value]) => (
              <label className="review-threshold" key={key}>
                {key}
                <input
                  type="number"
                  min={0}
                  max={key === 'topNExempt' ? 10 : 1}
                  step={key === 'topNExempt' ? 1 : 0.01}
                  value={value}
                  onChange={(e) =>
                    onThresholds({
                      ...thresholds,
                      [key]: Number(e.target.value),
                    })
                  }
                />
              </label>
            ))}
            {button('↺', () => onThresholds(SEVERITY_THRESHOLDS))}
          </details>
          <p>{t('review.ratingHelp')}</p>
          <p>{t('review.evaluationHelp')}</p>
          <p>{t('review.riskHelp')}</p>
          <p>{t('review.proxyHelp')}</p>
        </div>
      )}
    </section>
  )
}
