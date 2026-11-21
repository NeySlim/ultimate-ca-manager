/** The palette reaches the help of the current page: the way to it on a phone, where the bar hides its button. */
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

const helpResult = () => [...document.querySelectorAll('.command-result')].find((b) => b.textContent.includes('commandPalette.pageHelp'))

describe('CommandPalette, help of the page', () => {
  it('lists the help of the page and opens it, closing the palette', () => {
    const onOpenChange = vi.fn()
    const onOpenHelp = vi.fn()
    render(<CommandPalette open onOpenChange={onOpenChange} onOpenHelp={onOpenHelp} />)
    const result = helpResult()
    expect(result).toBeTruthy()
    expect(result.querySelector('.hint').textContent).toBe('common.help')
    fireEvent.click(result)
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(onOpenHelp).toHaveBeenCalledTimes(1)
  })

  it('finds it by its name or its hint, and leaves it out of other searches', () => {
    render(<CommandPalette open onOpenChange={vi.fn()} onOpenHelp={vi.fn()} />)
    const field = screen.getByRole('searchbox')
    fireEvent.change(field, { target: { value: 'pagehelp' } })
    expect(helpResult()).toBeTruthy()
    fireEvent.change(field, { target: { value: 'common.help' } })
    expect(helpResult()).toBeTruthy()
    fireEvent.change(field, { target: { value: 'trustStore' } })
    expect(helpResult()).toBeUndefined()
  })

  it('has no help entry on a page without help', () => {
    render(<CommandPalette open onOpenChange={vi.fn()} />)
    expect(helpResult()).toBeUndefined()
  })
})
