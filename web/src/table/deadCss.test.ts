import { describe, it, expect } from 'vitest'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

const SRC = resolve(process.cwd(), 'src')

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) return entry === 'proto' ? [] : sourceFiles(full)
    // Tests are excluded: this file names the dead classes as string literals,
    // so including it would make every class look "referenced".
    if (/\.test\.tsx?$/.test(entry)) return []
    return /\.tsx?$/.test(entry) ? [full] : []
  })
}

const ALL_SOURCE = sourceFiles(SRC).map((f) => readFileSync(f, 'utf8')).join('\n')
const TABLE_CSS = readFileSync(join(SRC, 'index.css'), 'utf8')

// The legacy per-direction seat layout, superseded by the BEM seat-hand /
// discard-lane system. Removed in PR 1b. If one of these ever comes back it
// must come back with a component that uses it -- otherwise it is dead again.
const REMOVED = [
  'hand-container',
  'hand-main-block',
  'hand-inner',
  'melds-container',
  'melds-main',
  'flowers-container',
  'discard-pool',
  'center-info-match',
  'center-info-status',
]

// The live layout classes. These are the control: they prove the "no component
// references it" check above can actually tell dead from live.
const LIVE = ['seat-bundle', 'discard-lane', 'center-seat', 'seat-meld-group']

describe('legacy seat-layout CSS', () => {
  it.each(REMOVED)('%s is referenced by no component', (cls) => {
    expect(ALL_SOURCE).not.toContain(cls)
  })

  it.each(REMOVED)('%s is absent from index.css', (cls) => {
    expect(TABLE_CSS).not.toContain(cls)
  })

  it.each(LIVE)('the live layout class %s is still used by components', (cls) => {
    expect(ALL_SOURCE).toContain(cls)
  })
})
