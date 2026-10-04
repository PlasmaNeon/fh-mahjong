import { getApiUrl } from '../../config'

// Field names/types are a cross-task contract with the backend
// (internal/review/report.go) — do not rename without updating that file.

export interface ActionProb {
  actionId: number
  prob: number
  evaluation?: { mean: number; standardError: number; samples: number }
}

export interface TileRisk {
  face: number
  unseen: number
  inHand: boolean
  anyRon: number
  standardError: number
  opponents: {
    seat: number
    ron: number
    contributors: { patternId: string; patternName: string; frequency: number; exampleFaces: number[] }[]
  }[]
}
export interface ReportDecision {
  id?: string
  positionIndex?: number
  choiceSource?: 'recorded' | 'inferred' | 'unknown'
  actualTileId?: number | null
  recommendedActionId?: number
  risk?: { method: string; samples: number; tiles: TileRisk[]; operations: { actionId: number; anyRon: number }[] }
  draw?: {
    actionIndex: number
    source: string
    hit: boolean
    chance: number
    unseen: number
    waits: { face: number; remaining: number; points: number }[]
  }

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
  study?: {
    eventWindow: number
    method: string
    objective: string
    units: string
    config: { worlds: number; riskWorlds: number; seed: number; maxDecisions: number }
    complete: boolean
    buildMillis: number
  }
  schemaVersion: number
  matchId: string
  ruleset: string
  checkpointPath: string
  checkpointStep: number
  // Content hash of the checkpoint that actually produced this report's
  // decisions (round 17, Finding 2) — survives a same-path hot reload,
  // unlike checkpointPath/checkpointStep. Omitted (empty/absent) when the
  // serving policy predates this field, meaning "unknown", not "no
  // checkpoint".
  checkpointSha256?: string
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

/**
 * POST to generate (or regenerate) the review report for a match.
 *
 * apiFetch must be the caller's authenticated fetch (useAuth().apiFetch) —
 * this route requires a session cookie + CSRF token as of round 21, Finding
 * 1 (an unauthenticated caller could otherwise spam ?force=1 against any
 * known match id and drive unbounded load against the policy server, which
 * is authenticated infrastructure shared with live RL agent traffic).
 */
export async function generateReview(
  matchId: string,
  apiFetch: (path: string, init?: RequestInit) => Promise<Response>,
): Promise<ReviewReport> {
  const res = await apiFetch(`/api/v1/matches/${matchId}/review`, { method: 'POST' })
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
