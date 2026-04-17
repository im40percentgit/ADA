/**
 * motion-tokens.test.ts — Verify motion design tokens are defined in tokens.css.
 *
 * Strategy: because vitest.config.ts sets `css: false`, jsdom never processes
 * stylesheets and `getComputedStyle` cannot see custom properties. Instead we
 * read tokens.css as raw text and assert that every expected token declaration
 * is present. This approach is simpler, has zero false-negatives from jsdom
 * CSS limitations, and directly tests the source of truth.
 *
 * @decision DEC-MOTION-001
 * @title Motion tokens as CSS custom properties in tokens.css
 * @status accepted
 * @rationale Zero-runtime, aligns with the existing token architecture where
 *   all design constants live as CSS custom properties on :root.
 */

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, it, expect } from 'vitest'

const TOKENS_CSS = resolve(__dirname, '../../../src/styles/tokens.css')
const BASE_CSS = resolve(__dirname, '../../../src/styles/base.css')

const tokensSource = readFileSync(TOKENS_CSS, 'utf-8')
const baseSource = readFileSync(BASE_CSS, 'utf-8')

describe('Motion tokens — tokens.css', () => {
  const expectedDurationTokens: [string, string][] = [
    ['--motion-duration-instant', '80ms'],
    ['--motion-duration-quick', '160ms'],
    ['--motion-duration-base', '240ms'],
    ['--motion-duration-slow', '400ms'],
  ]

  const expectedEasingTokens: [string, string][] = [
    ['--motion-ease-standard', 'cubic-bezier(0.2, 0, 0, 1)'],
    ['--motion-ease-emphasized', 'cubic-bezier(0.3, 0, 0, 1)'],
    ['--motion-ease-out', 'cubic-bezier(0, 0, 0.2, 1)'],
    ['--motion-ease-in', 'cubic-bezier(0.4, 0, 1, 1)'],
  ]

  it.each(expectedDurationTokens)(
    'defines %s with value %s',
    (token, value) => {
      // Match: --token-name: <value>; (allowing surrounding whitespace)
      const re = new RegExp(`${token}\\s*:\\s*${value}\\s*;`)
      expect(tokensSource).toMatch(re)
    }
  )

  it.each(expectedEasingTokens)(
    'defines %s with value %s',
    (token, value) => {
      // Escape parens for regex
      const escapedValue = value.replace(/[()]/g, '\\$&')
      const re = new RegExp(`${token}\\s*:\\s*${escapedValue}\\s*;`)
      expect(tokensSource).toMatch(re)
    }
  )

  it('declares all motion tokens inside :root', () => {
    // Find the :root block boundaries
    const rootStart = tokensSource.indexOf(':root {')
    const rootEnd = tokensSource.lastIndexOf('}')
    expect(rootStart).toBeGreaterThan(-1)
    const rootBlock = tokensSource.slice(rootStart, rootEnd + 1)
    expect(rootBlock).toContain('--motion-duration-instant')
    expect(rootBlock).toContain('--motion-ease-standard')
  })

  it('contains DEC-MOTION-001 annotation', () => {
    expect(tokensSource).toContain('DEC-MOTION-001')
  })
})

describe('Reduced-motion override — base.css', () => {
  it('has a prefers-reduced-motion: reduce media block', () => {
    expect(baseSource).toContain('prefers-reduced-motion: reduce')
  })

  it('zeros animation-duration inside the reduce block', () => {
    const reduceBlock = extractReducedMotionBlock(baseSource)
    expect(reduceBlock).toContain('animation-duration')
  })

  it('zeros transition-duration inside the reduce block', () => {
    const reduceBlock = extractReducedMotionBlock(baseSource)
    expect(reduceBlock).toContain('transition-duration')
  })

  it('contains DEC-MOTION-002 annotation', () => {
    expect(baseSource).toContain('DEC-MOTION-002')
  })
})

/**
 * Extract the content of the `@media (prefers-reduced-motion: reduce)` block.
 * Simple brace-counting approach — sufficient for a known-structure CSS file.
 */
function extractReducedMotionBlock(css: string): string {
  const marker = 'prefers-reduced-motion: reduce'
  const markerIdx = css.indexOf(marker)
  if (markerIdx === -1) return ''
  const openBrace = css.indexOf('{', markerIdx)
  if (openBrace === -1) return ''

  let depth = 1
  let i = openBrace + 1
  while (i < css.length && depth > 0) {
    if (css[i] === '{') depth++
    else if (css[i] === '}') depth--
    i++
  }
  return css.slice(openBrace, i)
}
