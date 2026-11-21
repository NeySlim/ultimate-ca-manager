/**
 * Regression tests: stored XSS in the ACME ToS preview
 * (security audit v2.203, item #14).
 *
 * The preview used to be built by a hand-rolled regex sanitizer whose output
 * was passed to dangerouslySetInnerHTML. It escaped `<`, `>` and `&` but NOT
 * double quotes, and it never validated link schemes, so admin-supplied ToS
 * text could break out of the generated href attribute or inject
 * `[click](javascript:...)` — stored XSS against any operator viewing the ACME
 * settings page. (The server CSP blocked inline script execution in modern
 * browsers, so this was defence-in-depth, not a full bypass.)
 *
 * The component now renders through ReactMarkdown, which builds React elements
 * instead of interpolating HTML, plus a urlTransform that pins link schemes.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { TosPreview } from '../ConfigTab'

const jsUrl = ['java', 'script:alert(1)'].join('')

describe('TosPreview', () => {
  it('renders ordinary markdown', () => {
    const { container } = render(<TosPreview body={'Hello **world**'} />)
    expect(screen.getByText('world').tagName).toBe('STRONG')
    expect(container.textContent).toContain('Hello')
  })

  it('renders nothing for empty input', () => {
    const { container } = render(<TosPreview body={'   '} />)
    expect(container.innerHTML).toBe('')
  })

  it('keeps a normal https link and hardens the anchor', () => {
    render(<TosPreview body={'[terms](https://example.com/tos)'} />)
    const link = screen.getByRole('link', { name: 'terms' })
    expect(link.getAttribute('href')).toBe('https://example.com/tos')
    expect(link.getAttribute('rel')).toContain('noopener')
    expect(link.getAttribute('target')).toBe('_blank')
  })

  it('strips a javascript: link target', () => {
    const { container } = render(<TosPreview body={`[click](${jsUrl})`} />)
    // The neutralised link renders as plain text — no anchor at all.
    expect(container.querySelector('a')).toBeNull()
    expect(container.textContent).toContain('click')
  })

  it('strips a data: link target', () => {
    const { container } = render(
      <TosPreview body={'[x](data:text/html;base64,PHNjcmlwdD4=)'} />
    )
    expect(container.querySelector('a')).toBeNull()
    expect(container.textContent).toContain('x')
  })

  it('enforces the allowlist beyond the library default', () => {
    // react-markdown's built-in defaultUrlTransform permits irc:; our
    // urlTransform does not. This is the test that fails if the custom
    // allowlist is removed, proving the prop is actually load-bearing.
    const { container } = render(<TosPreview body={'[chat](irc://host/chan)'} />)
    expect(container.querySelector('a')).toBeNull()
    expect(container.textContent).toContain('chat')
  })

  it('does not execute or inject raw HTML', () => {
    const payload = '<img src=x onerror="alert(1)">'
    const { container } = render(<TosPreview body={payload} />)
    // No real element is created; the markup survives as inert text.
    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('[onerror]')).toBeNull()
    expect(container.textContent).toContain('<img')
  })

  it('does not let a quote break out of an attribute', () => {
    // The old sanitizer did not escape `"`, so this closed the generated href
    // and injected a new attribute. The angle-bracket destination form makes
    // CommonMark actually parse the quoted payload as a link destination, so
    // the quote genuinely reaches attribute-generation code — the bare form
    // is rejected by the parser before any attribute is built.
    const bodies = [
      '[x](https://a" onmouseover="alert(1))',
      '[x](<https://a" onmouseover="alert(1)>)',
    ]
    for (const body of bodies) {
      const { container } = render(<TosPreview body={body} />)
      expect(container.querySelector('[onmouseover]')).toBeNull()
      for (const el of container.querySelectorAll('*')) {
        for (const attr of el.attributes) {
          expect(attr.name.toLowerCase().startsWith('on')).toBe(false)
        }
      }
    }
  })

  it('does not inject a script element', () => {
    const { container } = render(
      <TosPreview body={'<script>alert(1)</script>'} />
    )
    expect(container.querySelector('script')).toBeNull()
  })

  // The old sanitizer did three things plain CommonMark does not; remark-gfm,
  // remark-breaks and the shared markdown classes keep them working for
  // ToS text written against the old renderer (PR #247 review).

  it('autolinks a bare URL (remark-gfm)', () => {
    render(<TosPreview body={'See https://example.com/tos for details'} />)
    const link = screen.getByRole('link', { name: 'https://example.com/tos' })
    expect(link.getAttribute('href')).toBe('https://example.com/tos')
    expect(link.getAttribute('rel')).toContain('noopener')
  })

  it('still strips a bare javascript: autolink candidate', () => {
    const { container } = render(
      <TosPreview body={`Visit ${jsUrl} now`} />
    )
    for (const el of container.querySelectorAll('a')) {
      expect(el.getAttribute('href') ?? '').not.toContain('script:')
    }
  })

  it('renders a single newline as a hard break (remark-breaks)', () => {
    const { container } = render(
      <TosPreview body={'line one\nline two'} />
    )
    expect(container.querySelector('br')).not.toBeNull()
    expect(container.textContent).toContain('line one')
    expect(container.textContent).toContain('line two')
  })

  it('renders list markers as a real styled list', () => {
    const { container } = render(
      <TosPreview body={'- first\n- second'} />
    )
    const ul = container.querySelector('ul')
    expect(ul).not.toBeNull()
    expect(ul.querySelectorAll('li')).toHaveLength(2)
    // Under the zone's scope the browser's own bullets come back; the list is indented as the mockup's help lists
    expect(ul.style.paddingLeft).toBe('17px')
  })
})
