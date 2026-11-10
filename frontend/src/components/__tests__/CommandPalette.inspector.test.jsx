/**
 * A certificate or CA picked in the palette opens the inspector, the same one
 * a list row opens; the other types still go to their page.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  openEntity: vi.fn(), navigate: vi.fn(), globalSearch: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, fallback) => (typeof fallback === 'string' ? fallback : key), i18n: { language: 'en' } }),
}))
vi.mock('react-router-dom', () => ({ useNavigate: () => mocks.navigate }))
vi.mock('../../hooks/useOpenEntity', () => ({ useOpenEntity: () => mocks.openEntity }))
vi.mock('../../hooks', () => ({
  useAllRecentHistory: () => ({ allRecent: [], refreshHistory: vi.fn() }),
  useAllFavorites: () => ({ allFavorites: [], refreshFavorites: vi.fn() }),
}))
vi.mock('../../services', () => ({ searchService: { globalSearch: mocks.globalSearch } }))

import { CommandPalette } from '../CommandPalette'

describe('CommandPalette results', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.globalSearch.mockResolvedValue({
      certificates: [{ id: 7, name: 'web.example.com', subject: 'CN=web', status: 'valid' }],
      cas: [{ id: 3, name: 'Root CA', subject: 'CN=Root' }],
      users: [{ id: 5, name: 'alice', subject: 'alice@example.com' }],
    })
  })

  const search = async () => {
    const onOpenChange = vi.fn()
    render(<CommandPalette open onOpenChange={onOpenChange} />)
    fireEvent.change(screen.getByPlaceholderText('commandPalette.searchPlaceholder'), { target: { value: 'ex' } })
    return onOpenChange
  }

  it('opens a certificate in the inspector', async () => {
    const onOpenChange = await search()
    fireEvent.click(await screen.findByText('web.example.com'))
    expect(mocks.openEntity).toHaveBeenCalledWith('certificate', 7, expect.any(Object))
    expect(mocks.navigate).not.toHaveBeenCalled()
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('opens a CA in the inspector', async () => {
    await search()
    fireEvent.click(await screen.findByText('Root CA'))
    await waitFor(() => expect(mocks.openEntity).toHaveBeenCalledWith('ca', 3, expect.any(Object)))
  })

  it('sends a user to its page', async () => {
    await search()
    fireEvent.click(await screen.findByText('alice'))
    expect(mocks.navigate).toHaveBeenCalledWith('/users?selected=5')
    expect(mocks.openEntity).not.toHaveBeenCalled()
  })
})
