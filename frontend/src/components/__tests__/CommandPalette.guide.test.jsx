/** The palette opens the whole guide in a new tab, on the chapter of the current page, on a matching search. */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => ({ 'guide.paletteEntry': 'Guide', 'guide.paletteHint': 'Opens in a new tab' }[key] || key), i18n: { language: 'en' } }),
}))
vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }))
vi.mock('../../hooks/useOpenEntity', () => ({ useOpenEntity: () => vi.fn() }))
vi.mock('../../hooks', () => ({
  useAllRecentHistory: () => ({ allRecent: [], refreshHistory: vi.fn() }),
  useAllFavorites: () => ({ allFavorites: [], refreshFavorites: vi.fn() }),
}))
vi.mock('../../services', () => ({ searchService: { globalSearch: vi.fn().mockResolvedValue({}) } }))

import { CommandPalette } from '../CommandPalette'

const guide = () => [...document.querySelectorAll('.command-result')].find((b) => b.querySelector('.name')?.textContent === 'Guide')
const search = (value) => fireEvent.change(screen.getByRole('searchbox'), { target: { value } })

describe('CommandPalette, the guide', () => {
  it('is not listed in the empty palette, as the mockup', () => {
    render(<CommandPalette open onOpenChange={vi.fn()} guideHref="/guide/acme" />)
    expect(guide()).toBeUndefined()
  })

  it('opens the chapter of the page in a new tab and closes the palette', () => {
    const onOpenChange = vi.fn()
    const opened = vi.spyOn(window, 'open').mockImplementation(() => null)
    render(<CommandPalette open onOpenChange={onOpenChange} guideHref="/guide/acme" />)
    search('guid')
    expect(guide().querySelector('.hint').textContent).toBe('Opens in a new tab')
    fireEvent.click(guide())
    expect(opened).toHaveBeenCalledWith('/guide/acme', '_blank', 'noopener')
    expect(onOpenChange).toHaveBeenCalledWith(false)
    opened.mockRestore()
  })

  it('is found by its hint too, and left out of other searches', () => {
    render(<CommandPalette open onOpenChange={vi.fn()} />)
    search('new tab')
    expect(guide()).toBeTruthy()
    search('trustStore')
    expect(guide()).toBeUndefined()
  })
})
