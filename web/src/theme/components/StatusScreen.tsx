import type { ReactNode } from 'react'
import DirectShell from './DirectShell'

/** Route-level loading and recovery states share the ordinary app navigation. */
export default function StatusScreen({ title, description, actions, loading = false }: {
  title: string
  description?: string
  actions?: ReactNode
  loading?: boolean
}) {
  return <DirectShell title={title}>
    <section className="direct-status" aria-labelledby="page-status-title">
      {loading && <span className="direct-status__spinner" aria-hidden="true" />}
      <div role={loading ? 'status' : undefined}>
        <h1 id="page-status-title">{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className="direct-status__actions">{actions}</div>}
    </section>
  </DirectShell>
}
