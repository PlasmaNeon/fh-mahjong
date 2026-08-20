import { describe, it, expect } from 'vitest'
import { errorMessage, readJsonBody } from './apiJson'

function responseWith(body: () => unknown): Response {
  return { json: async () => body() } as unknown as Response
}

describe('readJsonBody', () => {
  it('returns the parsed body', async () => {
    expect(await readJsonBody(responseWith(() => ({ error: 'Seat taken' })))).toEqual({ error: 'Seat taken' })
  })

  it('returns an empty object when the body is absent or not JSON', async () => {
    expect(await readJsonBody(responseWith(() => { throw new Error('bad json') }))).toEqual({})
  })
})

describe('errorMessage', () => {
  it('prefers the server error', () => {
    expect(errorMessage({ error: 'Seat taken' }, 'Could not join')).toBe('Seat taken')
  })

  it('falls back when the server sent none', () => {
    expect(errorMessage({}, 'Could not join')).toBe('Could not join')
  })

  it('falls back on an empty server error, matching the || the callers used', () => {
    expect(errorMessage({ error: '' }, 'Could not join')).toBe('Could not join')
  })
})
