/**
 * The shared rows of Facts (components/atelier/facts): one rule of absence for the settings, the protocol docks and
 * the module docks; a copied value; a yes or no rule.
 */
import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k, p) => (p ? `${k} ${JSON.stringify(p)}` : k), i18n: { language: 'en' } }),
}))

import { Facts } from '../Detail'
import { fact, copyRow, yesNoState, isMissing } from '../facts'

describe('fact', () => {
  it('writes a value with its extras, and zero as a value', () => {
    expect(fact('Path', '/var/x', { kind: 'url', long: true })).toEqual({ label: 'Path', value: '/var/x', kind: 'url', long: true })
    expect(fact('Runs', 0)).toEqual({ label: 'Runs', value: 0 })
  })

  it('writes nothing, an empty text or false as the dash of absence, which takes none of the extras', () => {
    for (const none of [null, undefined, '', false]) {
      expect(fact('Note', none, { long: true, kind: 'hex' })).toEqual({ label: 'Note', absent: '—' })
    }
  })

  it('names an absence when told how', () => {
    expect(fact('Last test', null, { absent: 'Never', long: true })).toEqual({ label: 'Last test', absent: 'Never' })
    expect(fact('Last test', 'today', { absent: 'Never' })).toEqual({ label: 'Last test', value: 'today' })
  })

  it('draws a value and an absence as Facts rows', () => {
    render(<Facts items={[fact('Version', '3.0'), fact('Issuer', undefined, { long: true })]} />)
    const [value, absent] = document.querySelectorAll('dl.kv > div.row')
    expect(value.querySelector('dd.v')).toHaveTextContent('3.0')
    expect(absent).not.toHaveClass('long')
    expect(absent.querySelector('dd.absent')).toHaveTextContent('—')
  })
})

describe('copyRow and yesNoState', () => {
  it('copies a URL in its chip on a long row, an identifier in a chip without a kind, and keeps its extras on an absence', () => {
    expect(copyRow('URL', 'https://ca.example/est', 'url')).toMatchObject({ label: 'URL', value: 'https://ca.example/est', kind: 'url', long: true })
    expect(copyRow('Serial', 'AB:CD', 'hex')).toMatchObject({ kind: 'hex', long: false })
    expect(copyRow('Account', null, undefined, { long: true })).toEqual({ label: 'Account', absent: '—', long: true })
    render(<Facts items={[copyRow('Account', 'acct-1')]} />)
    expect(document.querySelector('dd.v .code-value:not(.url):not(.hex)')).toHaveTextContent('acct-1')
  })

  it('reads a rule as a state, and tells what is missing', () => {
    const t = (k) => k
    expect(yesNoState(t, true)).toEqual(['', 'common.yes', 'check'])
    expect(yesNoState(t, false)).toEqual(['muted', 'common.no', 'block'])
    expect([null, undefined, '', false, 0, 'x'].map(isMissing)).toEqual([true, true, true, true, false, false])
  })
})
