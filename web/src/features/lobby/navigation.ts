export type PlayIntent = 'quick-match'

type IntentStore = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>
const PLAY_INTENT_KEY = 'fh_play_intent'

export function rememberPlayIntent(store: IntentStore, intent: PlayIntent) {
  store.setItem(PLAY_INTENT_KEY, intent)
}

export function consumePlayIntent(store: IntentStore): PlayIntent | null {
  const value = store.getItem(PLAY_INTENT_KEY)
  store.removeItem(PLAY_INTENT_KEY)
  return value === 'quick-match' ? value : null
}

export function createPrivateTablePath(makeId: () => string = defaultTableId): string {
  return `/room/${makeId()}`
}

function defaultTableId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID().slice(0, 8)
  }
  return Math.random().toString(36).slice(2, 10)
}
