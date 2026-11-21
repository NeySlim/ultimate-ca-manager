/**
 * The palette lists each page under the name the bar or the Modules menu gives it, its menu group as the
 * hint (the mockup's commandResults, M:1305: « Vue d'ensemble · Navigation », « Modèles · PKI »), and
 * typing that name finds the page, in each of the ten languages.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { readFileSync, readdirSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const lang = vi.hoisted(() => ({ tree: {} }))
const lookup = (tree, key) => key.split('.').reduce((o, k) => (o == null ? o : o[k]), tree)

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => lookup(lang.tree, key) ?? key, i18n: { language: 'en' } }),
}))
vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }))
vi.mock('../../hooks/useOpenEntity', () => ({ useOpenEntity: () => vi.fn() }))
vi.mock('../../hooks', () => ({
  useAllRecentHistory: () => ({ allRecent: [], refreshHistory: vi.fn() }),
  useAllFavorites: () => ({ allFavorites: [], refreshFavorites: vi.fn() }),
}))
vi.mock('../../services', () => ({ searchService: { globalSearch: vi.fn().mockResolvedValue({}) } }))

import { CommandPalette } from '../CommandPalette'
import { MAIN_IDS, menuGroupsFor, menuLabelKey, moduleById } from '../../navigation/registry'

const localesDir = join(dirname(fileURLToPath(import.meta.url)), '../../i18n/locales')
const locales = Object.fromEntries(readdirSync(localesDir).filter((f) => f.endsWith('.json'))
  .map((f) => [f.replace('.json', ''), JSON.parse(readFileSync(join(localesDir, f), 'utf8'))]))

// Every page of the bar and of the Modules menu: [its name there, its group there]
const menuPages = () => [
  ...MAIN_IDS.map((id) => [moduleById(id).barKey, 'commands.categories.navigation']),
  ...menuGroupsFor().flatMap((g) => g.modules.map((m) => [menuLabelKey(m), g.labelKey])),
]
const results = () => [...document.querySelectorAll('.command-result')]
  .map((b) => `${b.querySelector('.name').textContent} · ${b.querySelector('.hint')?.textContent}`)

describe('the palette under the names of the menu', () => {
  beforeEach(() => { lang.tree = locales.fr })

  it('names the pages as the mockup does (fr)', () => {
    render(<CommandPalette open onOpenChange={vi.fn()} />)
    expect(results()).toEqual(expect.arrayContaining([
      'Vue d’ensemble · Navigation', 'Certificats · Navigation', 'Autorités · Navigation', 'Activité · Navigation',
      'Modèles · PKI', 'ACME · Protocoles', 'CRL / OCSP · Protocoles', 'Trust Store · PKI', 'HSM · Administration',
    ]))
  })

  it.each(Object.keys(locales))('%s: each name of the menu finds its page, its group as the hint', (code) => {
    lang.tree = locales[code]
    expect(Object.keys(locales)).toHaveLength(10)
    render(<CommandPalette open onOpenChange={vi.fn()} />)
    const field = screen.getByRole('searchbox')
    for (const [labelKey, groupKey] of menuPages()) {
      const name = lookup(lang.tree, labelKey)
      const group = lookup(lang.tree, groupKey)
      expect(typeof name, `${code}: ${labelKey}`).toBe('string')
      fireEvent.change(field, { target: { value: name } })
      expect(results(), `${code}: ${name}`).toContain(`${name} · ${group}`)
    }
  })
})
