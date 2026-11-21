/**
 * The palette is the mockup's command dialog: a search field, then one flat list of results.
 * Down from the field reaches the first result, the arrows move between them, up from the first
 * goes back to the field, Enter in the field runs the first one.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ navigate: vi.fn(), globalSearch: vi.fn() }))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, fallback) => (typeof fallback === 'string' ? fallback : key), i18n: { language: 'en' } }),
}))
vi.mock('react-router-dom', () => ({ useNavigate: () => mocks.navigate }))
vi.mock('../../hooks/useOpenEntity', () => ({ useOpenEntity: () => vi.fn() }))
vi.mock('../../hooks', () => ({
  useAllRecentHistory: () => ({ allRecent: [], refreshHistory: vi.fn() }),
  useAllFavorites: () => ({ allFavorites: [], refreshFavorites: vi.fn() }),
}))
vi.mock('../../services', () => ({ searchService: { globalSearch: mocks.globalSearch } }))

import { CommandPalette } from '../CommandPalette'

const field = () => screen.getByRole('searchbox')
const results = () => [...document.querySelectorAll('#command-results > .command-result')]

describe('CommandPalette: the mockup\'s dialog and keys', () => {
  beforeEach(() => { vi.clearAllMocks(); mocks.globalSearch.mockResolvedValue({}) })

  it('is the narrow dialog with the search label and one flat list of results', () => {
    render(<CommandPalette open onOpenChange={vi.fn()} />)
    const dialog = screen.getByTestId('command-palette')
    expect(dialog.tagName).toBe('DIALOG')
    expect(dialog).toHaveClass('narrow')
    expect(field()).toHaveFocus()
    expect(field().closest('label')).toHaveClass('command-search')
    expect(field().closest('label')).toHaveTextContent('commandPalette.searchLabel')
    expect(results().length).toBeGreaterThan(3)
    for (const r of results()) expect(r.querySelector('svg.icon') && r.querySelector('.name')).toBeTruthy()
  })

  it('moves from the field to the results and back with the arrows', () => {
    render(<CommandPalette open onOpenChange={vi.fn()} />)
    fireEvent.keyDown(field(), { key: 'ArrowDown' })
    expect(results()[0]).toHaveFocus()
    fireEvent.keyDown(results()[0], { key: 'ArrowDown' })
    expect(results()[1]).toHaveFocus()
    fireEvent.keyDown(results()[1], { key: 'ArrowUp' })
    expect(results()[0]).toHaveFocus()
    fireEvent.keyDown(results()[0], { key: 'ArrowUp' })
    expect(field()).toHaveFocus()
  })

  it('runs the first result on Enter in the field', () => {
    const onOpenChange = vi.fn()
    render(<CommandPalette open onOpenChange={onOpenChange} />)
    fireEvent.change(field(), { target: { value: 'users' } })
    const first = results()[0]
    expect(first).toBeTruthy()
    fireEvent.keyDown(field(), { key: 'Enter' })
    expect(mocks.navigate).toHaveBeenCalledTimes(1)
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })
})
