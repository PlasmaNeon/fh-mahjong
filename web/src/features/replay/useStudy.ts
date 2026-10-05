import { useEffect, useRef, useState } from 'react'
import { studyPath, studyRequest, type ApiFetch, type StudyJob, type StudySource } from './studyClient'
const terminal = new Set(['complete', 'failed', 'cancelled', 'interrupted'])
export function useStudy(source: StudySource, apiFetch: ApiFetch, authenticated: boolean) {
  const [job, setJob] = useState<StudyJob | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const generation = useRef(0)
  const identity = `${source.kind}:${source.id}`
  useEffect(() => {
    const current = ++generation.current
    const controller = new AbortController()
    setJob(null)
    setError('')
    setBusy(false)
    if (!authenticated) return
    void apiFetch(studyPath(source), { signal: controller.signal })
      .then(async (response) => {
        if (response.status === 404) return
        const body = await response.json()
        if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`)
        if (current === generation.current) setJob(body)
      })
      .catch((reason) => {
        if (!controller.signal.aborted && current === generation.current) setError(String(reason.message || reason))
      })
    return () => {
      controller.abort()
      ++generation.current
    }
  }, [identity, apiFetch, authenticated])
  useEffect(() => {
    if (!job || terminal.has(job.state)) return
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout>
    const current = generation.current
    const poll = async () => {
      try {
        const next = await studyRequest(apiFetch, `/api/v1/review-jobs/${encodeURIComponent(job.id)}`, {
          signal: controller.signal,
        })
        if (current !== generation.current || controller.signal.aborted) return
        setJob(next)
        setError('')
        if (!terminal.has(next.state)) timer = setTimeout(poll, 2000)
      } catch (reason) {
        if (!controller.signal.aborted && current === generation.current) {
          setError(reason instanceof Error ? reason.message : String(reason))
          timer = setTimeout(poll, 5000)
        }
      }
    }
    timer = setTimeout(poll, 1000)
    return () => {
      controller.abort()
      clearTimeout(timer)
    }
  }, [job?.id, job?.state, apiFetch])
  const run = async () => {
    const current = generation.current
    setBusy(true)
    setError('')
    try {
      const next = await studyRequest(apiFetch, studyPath(source), {
        method: 'POST',
      })
      if (current === generation.current) setJob(next)
    } catch (reason) {
      if (current === generation.current) setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      if (current === generation.current) setBusy(false)
    }
  }
  const cancel = async () => {
    if (!job) return
    const current = generation.current
    try {
      const next = await studyRequest(apiFetch, `/api/v1/review-jobs/${encodeURIComponent(job.id)}`, {
        method: 'DELETE',
      })
      if (current === generation.current) setJob(next)
    } catch (reason) {
      if (current === generation.current) setError(reason instanceof Error ? reason.message : String(reason))
    }
  }
  return {
    job,
    error,
    busy,
    run,
    cancel,
    running: busy || (!!job && !terminal.has(job.state)),
  }
}
