import { describe, it, expect } from 'vitest'
import { parseTokens } from './themeTokensParser'

const palette = (family, mode) => `
:root[data-theme="${family}"][data-mode="${mode}"] {
  --bg: #101010; --panel: #101010; --raised: #101010; --hover: #101010; --text: #ffffff;
  --muted: #cccccc; --line: #101010; --control: #101010; --accent: #3366ff; --selected: #101010;
  --good: #101010; --goodbg: #101010; --warn: #101010; --warn-fill: #101010; --warnbg: #101010;
  --bad: #101010; --badbg: #101010; --grad-a: #101010; --grad-b: #101010; --glow: x; --on-accent: #ffffff;
}`

describe('parseTokens alias blocks', () => {
  const css = `${palette('atelier', 'dark')}${palette('atelier', 'light')}
:root { --text-tertiary: var(--muted); }
:root[data-mode="light"] { --text-tertiary: var(--accent); }`

  it('applies a mode-scoped alias override only to palettes of that mode', () => {
    const t = parseTokens(css)
    expect(t['atelier-dark']['text-tertiary']).toBe('#cccccc')
    expect(t['atelier-light']['text-tertiary']).toBe('#3366ff')
  })
})
