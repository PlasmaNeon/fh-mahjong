import type { ReviewReport } from './reviewClient'
export type ApiFetch = (path: string, init?: RequestInit) => Promise<Response>
export type StudySource = { kind: 'match' | 'import'; id: string }
export type StudyJob = {
  id: string
  state: string
  completed: number
  total: number
  error: string
  report: ReviewReport | null
}
export type ReplayImport = {
  id: string
  filename: string
  sourceMatchId: string
  createdAt: string
}
export function studyPath(source: StudySource) {
  return source.kind === 'import'
    ? `/api/v1/replay-imports/${encodeURIComponent(source.id)}/review`
    : `/api/v1/matches/${encodeURIComponent(source.id)}/study`
}
export async function studyRequest(apiFetch: ApiFetch, path: string, init?: RequestInit): Promise<StudyJob> {
  const response = await apiFetch(path, init)
  const body = await response.json()
  if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`)
  return body as StudyJob
}
export async function uploadReplay(apiFetch: ApiFetch, file: File): Promise<ReplayImport> {
  const response = await apiFetch('/api/v1/replay-imports', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Paipu-Filename': encodeURIComponent(file.name),
    },
    body: await file.text(),
  })
  const body = await response.json()
  if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`)
  return body
}
