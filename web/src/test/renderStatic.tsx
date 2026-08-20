import { createElement, type ReactElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { I18nProvider } from '../i18n/I18nContext'

/**
 * Renders a component to static markup inside the app's i18n context — the
 * wrapper every component test needs, since vitest runs in the node
 * environment and components read `useI18n()`.
 */
export function renderStatic(node: ReactElement): string {
  return renderToStaticMarkup(createElement(I18nProvider, null, node))
}
