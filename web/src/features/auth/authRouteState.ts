import type { Location } from 'react-router-dom'

export type AuthRouteState = {
  backgroundLocation?: Location
  optionalAuth?: boolean
  cancelIntent?: 'quick-match'
}

export function resolveAuthDialogMode({
  hasBackground,
  optional,
  returnToParam,
}: {
  hasBackground: boolean
  optional: boolean
  returnToParam: string | null
}) {
  if (hasBackground && optional) return { dismissible: true, closeTo: null as string | null }
  if (!returnToParam) return { dismissible: true, closeTo: '/' }
  return { dismissible: false, closeTo: null as string | null }
}
