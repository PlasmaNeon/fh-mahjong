/**
 * Seat/prevailing wind labels.
 *
 * Winds are 1-based in the proto (East=1, South=2, West=3, North=4), so the
 * kanji table carries a blank at index 0 and stays indexable by wind directly.
 *
 * These are the TRADITIONAL forms used for table décor and seat plaques. The
 * jihai *tile* names in features/replay/reviewUtils.ts use simplified forms
 * (东/南/西/北) and cover seven faces including Haku/Hatsu/Chun — that is a
 * different data set and must not be merged with this one.
 */
export const WIND_KANJI = ['', '東', '南', '西', '北'] as const

/** Translation keys in seat order, for callers that render a localized wind. */
export const WIND_I18N_KEYS = [
  'common.east',
  'common.south',
  'common.west',
  'common.north',
] as const

export type WindI18nKey = (typeof WIND_I18N_KEYS)[number]

/** The translation key for a 1-based seat wind. */
export function windI18nKey(wind: number): WindI18nKey {
  return WIND_I18N_KEYS[wind - 1] ?? WIND_I18N_KEYS[0]
}
