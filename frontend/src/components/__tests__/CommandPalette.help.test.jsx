/** The palette reaches the help of the current page on a search only, after the pages and modules (mockup: no help entry). */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key, i18n: { language: 'en' } }),
}))
vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }))
vi.mock('../../hooks/useOpenEntity', () => ({ useOpenEntity: () => vi.fn() }))
vi.mock('../../hooks', () => ({
  useAllRecentHistory: () => ({ allRecent: [], refreshHistory: vi.fn() }),
  useAllFavorites: () => ({ allFavorites: [], refreshFavorites: vi.fn() }),
}))
vi.mock('../../services', () => ({ searchService: { globalSearch: vi.fn().mockResolvedValue({}) } }))

import { CommandPalette } from '../CommandPalette'

const results = () => [...document.querySelectorAll('.command-result')]
const helpResult = () => results().find((b) => b.textContent.includes('commandPalette.pageHelp'))
const search = (value) => fireEvent.change(screen.getByRole('searchbox'), { target: { value } })

describe('CommandPalette, help of the page', () => {
  it('starts the empty palette with the pages, as the mockup, without the help entry', () => {
    render(<CommandPalette open onOpenChange={vi.fn()} onOpenHelp={vi.fn()} />)
    expect(results().length).toBeGreaterThan(0)
    expect(helpResult()).toBeUndefined()
    expect(results()[0].textContent).not.toContain('commandPalette.pageHelp')
  })

  it('lists the help on a matching search and opens it, closing the palette', () => {
    const onOpenChange = vi.fn()
    const onOpenHelp = vi.fn()
    render(<CommandPalette open onOpenChange={onOpenChange} onOpenHelp={onOpenHelp} />)
    search('help')
    const result = helpResult()
    expect(result).toBeTruthy()
    expect(result.querySelector('.hint').textContent).toBe('common.help')
    fireEvent.click(result)
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(onOpenHelp).toHaveBeenCalledTimes(1)
  })

  it('places the help after the pages and modules the search also finds', () => {
    render(<CommandPalette open onOpenChange={vi.fn()} onOpenHelp={vi.fn()} />)
    search('e')
    const all = results()
    const help = all.indexOf(helpResult())
    expect(help).toBeGreaterThan(0)
    expect(help).toBe(all.length - 1)
  })

  it('finds it by its name or its hint, and leaves it out of other searches', () => {
    render(<CommandPalette open onOpenChange={vi.fn()} onOpenHelp={vi.fn()} />)
    search('pagehelp')
    expect(helpResult()).toBeTruthy()
    search('common.help')
    expect(helpResult()).toBeTruthy()
    search('trustStore')
    expect(helpResult()).toBeUndefined()
  })

  it('has no help entry on a page without help', () => {
    render(<CommandPalette open onOpenChange={vi.fn()} />)
    search('help')
    expect(helpResult()).toBeUndefined()
  })
})
