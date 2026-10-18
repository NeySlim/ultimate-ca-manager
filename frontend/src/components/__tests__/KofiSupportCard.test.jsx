import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const state = vi.hoisted(() => ({ auth: {}, admin: true }))

const mocks = vi.hoisted(() => ({ updatePreferences: vi.fn() }))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

// The real preferences store runs; only its PUT is captured.
vi.mock('../../services/account.service', () => ({
  accountService: { updatePreferences: mocks.updatePreferences },
}))

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => state.auth,
}))

vi.mock('../../hooks/usePermission', () => ({
  usePermission: () => ({ isAdmin: () => state.admin }),
}))

import { KofiSupportCard } from '../KofiSupportCard'
import { applyServerPreferences, setAuthenticated } from '../../stores/userPreferencesStore'

const renderCard = (version) => render(
  <MemoryRouter><KofiSupportCard version={version} /></MemoryRouter>,
)

const loadServerPrefs = (prefs) => act(() => { applyServerPreferences(prefs) })

const settle = () => act(async () => { await new Promise((r) => setTimeout(r, 0)) })

describe('KofiSupportCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.updatePreferences.mockResolvedValue({})
    setAuthenticated(false)
    setAuthenticated(true)
    state.auth = { user: { id: 1 }, forcePasswordChange: false, mustEnroll2fa: false }
    state.admin = true
  })

  afterEach(() => {
    document.querySelectorAll('[data-test-dialog]').forEach((el) => el.remove())
  })

  it('shows for an admin on a fresh install', async () => {
    renderCard('2.242')
    await loadServerPrefs({})
    expect(screen.getByText('kofi.message')).toBeInTheDocument()
    const link = screen.getByRole('link', { name: 'kofi.support' })
    expect(link).toHaveAttribute('href', 'https://ko-fi.com/neyslim')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('shows for an admin when the version changed since the last dismissal', async () => {
    await loadServerPrefs({ kofi_seen_version: '2.241' })
    renderCard('2.242')
    expect(screen.getByText('kofi.message')).toBeInTheDocument()
  })

  it('does not show for a non-admin', async () => {
    state.admin = false
    await loadServerPrefs({})
    renderCard('2.242')
    await settle()
    expect(screen.queryByText('kofi.message')).not.toBeInTheDocument()
  })

  it('does not show again for the version already dismissed', async () => {
    await loadServerPrefs({ kofi_seen_version: '2.242' })
    renderCard('2.242')
    await settle()
    expect(screen.queryByText('kofi.message')).not.toBeInTheDocument()
  })

  it('waits for the server prefs, and the dismissal keeps all of them', async () => {
    renderCard('2.242')
    await settle()
    expect(screen.queryByText('kofi.message')).not.toBeInTheDocument()

    await loadServerPrefs({ language: 'fr', theme_mode: 'dark', update_popup_seen_version: '2.241' })
    fireEvent.click(screen.getByRole('button', { name: 'kofi.dismiss' }))
    expect(mocks.updatePreferences).toHaveBeenCalledTimes(1)
    expect(mocks.updatePreferences).toHaveBeenCalledWith({
      language: 'fr', theme_mode: 'dark', update_popup_seen_version: '2.241', kofi_seen_version: '2.242',
    })
  })

  it('closing records the version, then stays hidden until the next version', async () => {
    await loadServerPrefs({ language: 'en' })
    const first = renderCard('2.242')
    fireEvent.click(screen.getByRole('button', { name: 'kofi.dismiss' }))
    expect(mocks.updatePreferences).toHaveBeenCalledWith({ language: 'en', kofi_seen_version: '2.242' })
    expect(screen.queryByText('kofi.message')).not.toBeInTheDocument()
    first.unmount()

    const again = renderCard('2.242')
    await settle()
    expect(screen.queryByText('kofi.message')).not.toBeInTheDocument()
    again.unmount()

    renderCard('2.243')
    expect(screen.getByText('kofi.message')).toBeInTheDocument()
  })

  it('following the link records the version too', async () => {
    await loadServerPrefs({})
    renderCard('2.242')
    fireEvent.click(screen.getByRole('link', { name: 'kofi.support' }))
    expect(mocks.updatePreferences).toHaveBeenCalledWith({ kofi_seen_version: '2.242' })
    expect(screen.queryByText('kofi.message')).not.toBeInTheDocument()
  })

  it('waits for an open dialog to close before showing', async () => {
    const dialog = document.createElement('div')
    dialog.setAttribute('role', 'dialog')
    dialog.setAttribute('data-state', 'open')
    dialog.setAttribute('data-test-dialog', '')
    document.body.appendChild(dialog)

    await loadServerPrefs({})
    renderCard('2.242')
    await settle()
    expect(screen.queryByText('kofi.message')).not.toBeInTheDocument()

    await act(async () => { dialog.remove() })
    await waitFor(() => expect(screen.getByText('kofi.message')).toBeInTheDocument())
  })

  it('does not show during the forced password change', async () => {
    state.auth = { ...state.auth, forcePasswordChange: true }
    await loadServerPrefs({})
    renderCard('2.242')
    await settle()
    expect(screen.queryByText('kofi.message')).not.toBeInTheDocument()
  })
})
