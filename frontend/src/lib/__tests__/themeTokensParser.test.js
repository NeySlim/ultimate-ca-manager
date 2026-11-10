import { describe, it, expect } from 'vitest'
import { parseTokens, paletteDecls } from './themeTokensParser'

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

describe('paletteDecls alias blocks', () => {
  const css = `${palette('atelier', 'dark')}${palette('atelier', 'light')}
:root { --violet: #111111; }
:root[data-mode="light"] { --violet: #222222; }
:root, :root[data-mode="dark"] { --grouped: #333333; }`

  it('scopes a mode alias override to palettes of that mode', () => {
    const d = paletteDecls('', css)
    expect(d['atelier-dark'].violet).toBe('#111111')
    expect(d['atelier-light'].violet).toBe('#222222')
  })

  it('reads a grouped selector list: a bare :root applies to both modes', () => {
    const d = paletteDecls('', css)
    expect(d['atelier-dark'].grouped).toBe('#333333')
    expect(d['atelier-light'].grouped).toBe('#333333')
  })
})
