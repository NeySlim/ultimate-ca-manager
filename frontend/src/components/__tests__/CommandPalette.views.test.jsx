/**
 * The views of the protocol pages in the palette: found by their name (the page, then the view), opened
 * at their ?tab= address, never listed before a search (the list of pages stays the mockup's).
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const lang = vi.hoisted(() => ({ tree: {} }))
const nav = vi.hoisted(() => ({ navigate: null }))
const lookup = (tree, key) => key.split('.').reduce((o, k) => (o == null ? o : o[k]), tree)
const interpolate = (text, params) => (params ? text.replace(/\{\{(\w+)\}\}/g, (_, k) => params[k] ?? '') : text)

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, params) => interpolate(lookup(lang.tree, key) ?? key, params), i18n: { language: 'en' } }),
}))
vi.mock('react-router-dom', () => ({ useNavigate: () => nav.navigate }))
vi.mock('../../hooks/useOpenEntity', () => ({ useOpenEntity: () => vi.fn() }))
vi.mock('../../hooks', () => ({
  useAllRecentHistory: () => ({ allRecent: [], refreshHistory: vi.fn() }),
  useAllFavorites: () => ({ allFavorites: [], refreshFavorites: vi.fn() }),
}))
vi.mock('../../services', () => ({ searchService: { globalSearch: vi.fn().mockResolvedValue({}) } }))

import { CommandPalette } from '../CommandPalette'

const localesDir = join(dirname(fileURLToPath(import.meta.url)), '../../i18n/locales')
const locale = (code) => JSON.parse(readFileSync(join(localesDir, `${code}.json`), 'utf8'))
const results = () => [...document.querySelectorAll('.command-result')]
  .map((b) => `${b.querySelector('.name').textContent} · ${b.querySelector('.hint')?.textContent}`)
const can = (perms) => ({ isAdmin: () => perms.includes('*'), hasPermission: (p) => perms.includes('*') || perms.includes(p) })
const type = (text) => fireEvent.change(screen.getByRole('searchbox'), { target: { value: text } })

describe('the views of the protocol pages in the palette', () => {
  beforeEach(() => {
    lang.tree = locale('en')
    nav.navigate = vi.fn()
  })

  it('lists no view before a search', () => {
    render(<CommandPalette open onOpenChange={vi.fn()} />)
    expect(results().some((r) => r.includes('DNS providers'))).toBe(false)
    expect(results().some((r) => r.startsWith('ACME · '))).toBe(true)
  })

  it('finds a view by its name and opens it at its address', () => {
    const onOpenChange = vi.fn()
    render(<CommandPalette open onOpenChange={onOpenChange} />)
    type('dns prov')
    expect(results()).toEqual(['ACME: DNS providers · Protocols'])
    fireEvent.click(screen.getByRole('button', { name: /ACME: DNS providers/ }))
    expect(nav.navigate).toHaveBeenCalledWith('/acme?tab=dns')
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('names the page of each view, which tells the configurations apart', () => {
    render(<CommandPalette open onOpenChange={vi.fn()} />)
    type('configuration')
    expect(results()).toEqual(expect.arrayContaining(['SCEP: Configuration · Protocols', 'EST: Configuration · Protocols', 'TSA: Configuration · Protocols']))
  })

  it('finds a view by its page name too, in the language of the interface', () => {
    lang.tree = locale('fr')
    render(<CommandPalette open onOpenChange={vi.fn()} />)
    type('acme')
    expect(results()).toEqual(expect.arrayContaining(['ACME : Réglages du serveur · Protocoles', 'ACME : Certificats émis · Protocoles']))
  })

  it('offers no view of a page the account may not open', () => {
    render(<CommandPalette open onOpenChange={vi.fn()} can={can(['read:certificates', 'read:scep'])} />)
    type('configuration')
    expect(results()).toEqual(['SCEP: Configuration · Protocols'])
  })
})
