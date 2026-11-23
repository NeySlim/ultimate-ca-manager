/**
 * Facts, the typed rows of terms and values (KV-2): a plain pair, a state, an absent value, a digest and a URL
 * that copy whole, an action apart from the value, a help folded behind its button; Props keeps its flat list.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'

const showSuccess = vi.hoisted(() => vi.fn())
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k, p) => (p ? `${k} ${JSON.stringify(p)}` : k), i18n: { language: 'en' } }),
}))
vi.mock('../../../contexts/NotificationContext', () => ({ useNotification: () => ({ showSuccess, showError: vi.fn() }) }))

import { Facts, FactsGroup, FactRow, CodeValue, RowAction, Props } from '../Detail'
import { hexLines } from '../helpers'

const URL = 'http://ca.example.org/cdp/7c1e2a40-55b3-4d9e-a1f6-0b8d3e9f2c11.crl'
const SHA256 = Array.from({ length: 32 }, (_, i) => (i * 7 + 16).toString(16).toUpperCase().padStart(2, '0').slice(-2)).join(':')
let writeText

beforeEach(() => {
  showSuccess.mockClear()
  writeText = vi.fn().mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
  Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true })
})

const rows = () => [...document.querySelectorAll('dl.kv > div.row')]

describe('Facts', () => {
  it('draws a plain pair as a row: its term, then its value', () => {
    render(<Facts items={[['Algorithm', 'RSA 4096'], null, ['Storage', 'Software']]} />)
    expect(rows()).toHaveLength(2)
    const [first] = rows()
    expect([...first.children].map((c) => c.tagName)).toEqual(['DT', 'DD'])
    expect(first.querySelector('dt')).toHaveTextContent('Algorithm')
    expect(first.querySelector('dd')).toHaveClass('v')
    expect(first.querySelector('dd')).toHaveTextContent('RSA 4096')
  })

  it('writes a state as a pill and an absent value muted, without the value class', () => {
    render(<Facts items={[{ label: 'OCSP', state: ['muted', 'Off'] }, { label: 'Profile', absent: 'None' }]} />)
    const [state, absent] = rows()
    expect(state.querySelector('dd.v .badge.muted')).toHaveTextContent('Off')
    const dd = absent.querySelector('dd')
    expect(dd).toHaveTextContent('None')
    expect(dd).toHaveClass('absent')
    expect(dd).not.toHaveClass('v')
  })

  it('puts the action apart from the value, a write button', () => {
    const run = vi.fn()
    render(<Facts items={[{ label: 'Pickers', value: 'Listed', action: <RowAction onClick={run}>Hide</RowAction> }]} />)
    const [row] = rows()
    expect(row.querySelector('dd.v')).toHaveTextContent(/^Listed$/)
    const button = screen.getByRole('button', { name: 'Hide' })
    expect(button.closest('dd')).toHaveClass('act')
    expect(button).toHaveAttribute('data-write', '')
    fireEvent.click(button)
    expect(run).toHaveBeenCalledTimes(1)
  })

  it('folds a help behind a button that names and controls it', () => {
    render(<Facts items={[{ label: 'Unique subject', value: 'Not enforced', help: 'When enforced, a subject is unique.' }]} />)
    const tip = screen.getByRole('button', { name: 'common.helpAbout {"name":"Unique subject"}' })
    const help = document.getElementById(tip.getAttribute('aria-controls'))
    expect(help.tagName).toBe('DD')
    expect(help).toHaveClass('help')
    expect(help).toHaveTextContent('When enforced, a subject is unique.')
    expect(tip).toHaveAttribute('aria-expanded', 'false')
    expect(help).not.toBeVisible()
    fireEvent.click(tip)
    expect(tip).toHaveAttribute('aria-expanded', 'true')
    expect(help).toBeVisible()
    expect(tip.closest('dt')).not.toBeNull()
  })

  it('copies a URL cut in its middle whole, shows it whole in its title and on a click', async () => {
    render(<Facts items={[{ label: 'CRL distribution point', value: URL, kind: 'url', long: true }]} />)
    const [row] = rows()
    expect(row).toHaveClass('long')
    const shown = row.querySelector('.code-value .val')
    expect(shown).toHaveAttribute('title', URL)
    expect(shown.querySelector('.tail')).toHaveTextContent(URL.slice(-14))
    expect(shown).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(shown)
    expect(shown).toHaveAttribute('aria-expanded', 'true')
    fireEvent.click(screen.getByRole('button', { name: 'protocols.copyValue {"name":"CRL distribution point"}' }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(URL))
    expect(showSuccess).toHaveBeenCalledWith('common.copied')
  })

  it('draws a digest in equal lines and copies it as it is written', async () => {
    render(<CodeValue value={SHA256} kind="hex" label="SHA-256" />)
    const lines = [...document.querySelectorAll('.code-value .val.hex > .line')].map((l) => l.textContent)
    expect(lines).toHaveLength(4)
    expect(lines.map((l) => l.replace(/:$/, '').split(':').length)).toEqual([8, 8, 8, 8])
    fireEvent.click(screen.getByRole('button', { name: 'protocols.copyValue {"name":"SHA-256"}' }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(SHA256))
  })

  it('cuts a digest in equal lines no wider than the room it is given', () => {
    const sha1 = SHA256.split(':').slice(0, 20).join(':')
    const sizes = (text, room) => hexLines(text, room).split('\n').map((l) => l.replace(/:$/, '').split(':').length)
    expect(sizes(sha1, 10)).toEqual([10, 10])
    expect(sizes(sha1, 9)).toEqual([5, 5, 5, 5])
    expect(sizes(sha1, 4)).toEqual([4, 4, 4, 4, 4])
    expect(sizes(SHA256, 7)).toEqual([4, 4, 4, 4, 4, 4, 4, 4])
    expect(sizes(SHA256, 40)).toEqual([8, 8, 8, 8])
    expect(sizes(sha1, 0)).toEqual([1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1])
    // twelve bytes: two lines of six, not ten and two
    expect(sizes(SHA256.split(':').slice(0, 12).join(':'))).toEqual([6, 6])
    // a prime count: lines as even as they can be
    expect(sizes(SHA256.split(':').slice(0, 19).join(':'), 10)).toEqual([10, 9])
    expect(hexLines(sha1, 3).replace(/\n/g, '')).toBe(sha1)
  })

  it('fits the lines of a digest to the width of its column, and copies it whole', async () => {
    const sha1 = SHA256.split(':').slice(0, 20).join(':')
    let observed
    const RO = window.ResizeObserver
    window.ResizeObserver = class { constructor(cb) { observed = cb } observe() {} disconnect() {} }
    let room = 400
    // 7 px a character, the chip's padding, gap and button 38 px
    const rect = vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function () {
      const el = this
      const width = el.classList.contains('line') ? el.textContent.length * 7
        : el.classList.contains('code-value') ? Math.min(room, Math.max(...[...el.querySelectorAll('.line')].map((l) => l.textContent.length * 7)) + 38)
          : el.classList.contains('val') ? Math.min(room, Math.max(...[...el.querySelectorAll('.line')].map((l) => l.textContent.length * 7)) + 38) - 38
            : el.tagName === 'DD' ? room : 0
      return { width, height: 0, top: 0, left: 0, right: width, bottom: 0, x: 0, y: 0 }
    })
    try {
      render(<Facts items={[{ label: 'SHA-1', value: sha1, kind: 'hex' }]} />)
      const sizes = () => [...document.querySelectorAll('.code-value .val.hex > .line')].map((l) => l.textContent.replace(/:$/, '').split(':').length)
      expect(sizes()).toEqual([10, 10])
      room = 200 // 162 px for the text: 23 characters, 7 bytes at most
      act(() => observed([]))
      expect(sizes()).toEqual([5, 5, 5, 5])
      room = 400
      act(() => observed([]))
      expect(sizes()).toEqual([10, 10])
      fireEvent.click(screen.getByRole('button', { name: 'protocols.copyValue {"name":"SHA-1"}' }))
      await waitFor(() => expect(writeText).toHaveBeenCalledWith(sha1))
    } finally {
      rect.mockRestore()
      window.ResizeObserver = RO
    }
  })

  it('splits a 20-byte serial in two lines of ten, and leaves a value that is not colon hex whole', () => {
    const serial = '4A:1F:C2:09:7E:B3:55:D0:8C:21:6F:E4:13:9A:B7:02:DD:58:31:C6'
    expect(hexLines(serial)).toBe('4A:1F:C2:09:7E:B3:55:D0:8C:21:\n6F:E4:13:9A:B7:02:DD:58:31:C6')
    expect(hexLines('01:02')).toBe('01:02')
    expect(hexLines('not hex at all')).toBe('not hex at all')
  })

  it('marks the rows the mockup does not have, and takes rows as children', () => {
    render(<Facts items={[{ label: 'Signature', value: 'SHA-256', product: true }]}><FactRow label="Scheme" value="PSS" /></Facts>)
    const [a, b] = rows()
    expect(a.querySelector('dt')).toHaveAttribute('data-product', '')
    expect(a.querySelector('dd')).toHaveAttribute('data-product', '')
    expect(b.querySelector('dt')).toHaveTextContent('Scheme')
    expect(b.querySelector('dt')).not.toHaveAttribute('data-product')
  })

  it('shares one label column between the sections of a group', () => {
    render(<FactsGroup><section><Facts items={[['A', '1']]} /></section><section><Facts items={[['B', '2']]} /></section></FactsGroup>)
    expect(document.querySelectorAll('.kvg > section > dl.kv')).toHaveLength(2)
  })
})

describe('Props', () => {
  it('keeps its flat list of terms and values', () => {
    render(<Props items={[['Key', 'RSA'], null, ['Mode', 'Auto']]} />)
    const dl = document.querySelector('dl.props')
    expect([...dl.children].map((c) => `${c.tagName}:${c.textContent}`)).toEqual(['DT:Key', 'DD:RSA', 'DT:Mode', 'DD:Auto'])
  })
})
