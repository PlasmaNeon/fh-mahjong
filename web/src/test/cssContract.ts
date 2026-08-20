import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

/**
 * Reads stylesheet sources by path relative to the web/ package root and joins
 * them. Missing files are skipped, so a caller can list optional stylesheets.
 */
export function readSourceCss(...relPaths: string[]): string {
  return relPaths
    .map((path) => resolve(process.cwd(), path))
    .filter((path) => existsSync(path))
    .map((path) => readFileSync(path, 'utf8'))
    .join('\n')
}

/** Returns the declaration block of the first rule matching `selector`. */
export function ruleBody(css: string, selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return css.match(new RegExp(`${escaped}\\s*\\{([^}]*)\\}`))?.[1] ?? ''
}

/** Reads a `--name: <n>px` custom property out of a declaration block. */
export function pixelVariable(rule: string, name: string): number {
  const value = rule.match(new RegExp(`${name}:\\s*([\\d.]+)px`))?.[1]
  return Number(value)
}
