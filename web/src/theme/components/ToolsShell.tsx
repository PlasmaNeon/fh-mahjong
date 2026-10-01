import type { ReactNode } from 'react'
import DirectShell from './DirectShell'

/** Tool state stays owned by each workbench; navigation uses the real app routes. */
export default function ToolsShell({ children, title }: { children: ReactNode; title: string }) {
  return <DirectShell title={title}><h1 className="direct-tools-sr-only">{title}</h1>{children}</DirectShell>
}
