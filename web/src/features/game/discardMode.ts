export type DiscardMode = 'single' | 'double'

const DISCARD_MODE_KEY = 'mahjong_discard_mode_v1'
const DEFAULT_MODE: DiscardMode = 'double'

export function parseDiscardMode(raw: string | null): DiscardMode {
  return raw === 'single' || raw === 'double' ? raw : DEFAULT_MODE
}

function getLocalStorage(): Storage | null {
  if (typeof window === 'undefined') return null
  return window.localStorage
}

export function loadDiscardMode(): DiscardMode {
  const storage = getLocalStorage()
  if (!storage) return DEFAULT_MODE
  return parseDiscardMode(storage.getItem(DISCARD_MODE_KEY))
}

export function saveDiscardMode(mode: DiscardMode): void {
  getLocalStorage()?.setItem(DISCARD_MODE_KEY, mode)
}
