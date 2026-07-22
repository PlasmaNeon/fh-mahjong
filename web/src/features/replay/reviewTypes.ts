import { getApiUrl } from '../../config'

// Field names/types are a cross-task contract with the backend
// (internal/review/report.go) — do not rename without updating that file.

export interface ActionProb {
  actionId: number
  prob: number
}

export interface ReportDecision {
  seat: number
  round: number
  actionIndex: number
  chosenActionId: number
  chosenProb: number
  // null when the report's valuesCalibrated is false (a privileged-critic
  // checkpoint served this decision) — see ReviewReport.valuesCalibrated.
  value: number | null
  actions: ActionProb[]
}

export interface GapRef {
  decision: number
  gap: number
}

export interface SeatSummary {
  seat: number
  decisions: number
  meanChosenProb: number
  topGaps: GapRef[]
}

export interface ReviewReport {
  schemaVersion: number
  matchId: string
  ruleset: string
  checkpointPath: string
  checkpointStep: number
  generatedAt: string
  decisions: ReportDecision[]
  seats: SeatSummary[]
  // False when the served checkpoint is a privileged-critic model: every
  // ReportDecision.value in this report is null rather than a number.
  // Action-ranking fields (actions/chosenProb/topGaps) are unaffected.
  //
  // undefined/absent for every cached report generated before this field
  // existed (schema v1, pre-B2c): those reports always carried real numeric
  // decision values, so absence must NOT be treated the same as explicit
  // `false` — see resolveValuesCalibrated in reviewUtils.ts, which is what
  // callers should use instead of reading this field directly.
  valuesCalibrated?: boolean
}

/** GET the review report for a match. Returns null if none exists yet (404). */
export async function fetchReview(matchId: string): Promise<ReviewReport | null> {
  const res = await fetch(getApiUrl(`/api/v1/matches/${matchId}/review`))
  if (res.status === 404) {
    return null
  }
  if (!res.ok) {
    const message = await extractErrorMessage(res)
    throw { status: res.status, message }
  }
  return (await res.json()) as ReviewReport
}

/** POST to generate (or regenerate) the review report for a match. */
export async function generateReview(matchId: string): Promise<ReviewReport> {
  const res = await fetch(getApiUrl(`/api/v1/matches/${matchId}/review`), { method: 'POST' })
  if (!res.ok) {
    const message = await extractErrorMessage(res)
    throw { status: res.status, message }
  }
  return (await res.json()) as ReviewReport
}

async function extractErrorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json()
    if (body && typeof body.error === 'string') {
      return body.error
    }
  } catch {
    // fall through to generic message
  }
  return `HTTP ${res.status}`
}
