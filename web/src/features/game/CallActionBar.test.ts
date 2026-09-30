import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { game } from '../../proto/game'
import { I18nProvider } from '../../i18n/I18nContext'
import { CallActionBar, callActionKey, uniqueCallChoices } from './CallActionBar'

const tile = (id: number, value: number) => ({ id, suit: game.Suit.SUIT_SOU, value })
const lower = { type: game.ActionType.ACTION_CHII, meldTiles: [tile(0, 1), tile(1, 2)] }
const middle = { type: game.ActionType.ACTION_CHII, meldTiles: [tile(1, 2), tile(3, 4)] }
const kan = (value: number) => ({ type: game.ActionType.ACTION_KAN, meldTiles: [0, 1, 2, 3].map(id => tile(id + value * 4, value)) })

describe('call action choices', () => {
  it('deduplicates equivalent copies while retaining the exact original server action, including tile zero', () => {
    const sameFaces = { ...lower, meldTiles: [tile(11, 2), tile(10, 1)] }
    const choices = uniqueCallChoices([lower, sameFaces, middle])
    expect(choices).toEqual([lower, middle])
    expect(choices[0]).toBe(lower)
    expect(choices[0].meldTiles?.[0].id).toBe(0)
  })
  it('retains different kan faces and added versus closed kan payloads', () => {
    const added = { type: game.ActionType.ACTION_KAN, meldTiles: [tile(7, 1)] }
    expect(uniqueCallChoices([kan(1), kan(2), added])).toHaveLength(3)
  })
  it('invalidates choices on a new discard, round or physical action IDs', () => {
    expect(callActionKey([lower], 'round1:discard0')).not.toBe(callActionKey([lower], 'round1:discard1'))
    expect(callActionKey([lower], 'round1')).not.toBe(callActionKey([lower], 'round2'))
    expect(callActionKey([lower], 'turn')).not.toBe(callActionKey([{ ...lower, meldTiles: [tile(20, 1), tile(21, 2)] }], 'turn'))
    expect(callActionKey([lower], 'turn')).toBe(callActionKey([{ ...lower }], 'turn'))
  })
  it('renders one CHII and one KAN trigger with an explicit pass', () => {
    const html = renderToStaticMarkup(createElement(I18nProvider, null,
      createElement(CallActionBar, { actions: [lower, middle, kan(1), kan(2)], contextKey: 'turn', allowPass: true, onAction: () => {} })))
    expect(html.match(/>Chii<\/button>/g)).toHaveLength(1)
    expect(html.match(/>Kan<\/button>/g)).toHaveLength(1)
    expect(html).toContain('>Pass</button>')
    expect(html.match(/aria-haspopup="true"/g)).toHaveLength(2)
  })
  it('does not offer passing on a normal turn with kan choices', () => {
    const html = renderToStaticMarkup(createElement(I18nProvider, null,
      createElement(CallActionBar, { actions: [kan(1), kan(2)], contextKey: 'turn', onAction: () => {} })))
    expect(html).not.toContain('>Pass</button>')
  })
})
