import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const state = vi.hoisted(() => ({
  serverPrefs: {},
  auth: {},
  admin: true,
}))

const mocks = vi.hoisted(() => ({
  getPreferences: vi.fn(),
  persistPreference: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

vi.mock('../../services', () => ({
  accountService: { getPreferences: mocks.getPreferences },
}))

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => state.auth,
}))

vi.mock('../../hooks/usePermission', () => ({
  usePermission: () => ({ isAdmin: () => state.admin }),
}))

vi.mock('../../stores/userPreferencesStore', () => ({
  persistPreference: mocks.persistPreference,
}))

import { KofiSupportCard } from '../KofiSupportCard'

const renderCard = (version) => render(
  <MemoryRouter><KofiSupportCard version={version} /></MemoryRouter>,
)

// Lets the preferences request settle before asserting absence.
const settle = () => act(async () => { await new Promise((r) => setTimeout(r, 0)) })

describe('KofiSupportCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    state.serverPrefs = {}
    state.auth = { user: { id: 1 }, forcePasswordChange: false, mustEnroll2fa: false }
    state.admin = true
    mocks.getPreferences.mockImplementation(async () => ({ data: { ...state.serverPrefs } }))
    mocks.persistPreference.mockImplementation(async (key, value) => {
      state.serverPrefs = { ...state.serverPrefs, [key]: value }
    })
  })

  afterEach(() => {
    document.querySelectorAll('[data-test-dialog]').forEach((el) => el.remove())
  })

  it('shows for an admin on a fresh install', async () => {
    renderCard('2.242')
    expect(await screen.findByText('kofi.message')).toBeInTheDocument()
    const link = screen.getByRole('link', { name: 'kofi.support' })
    expect(link).toHaveAttribute('href', 'https://ko-fi.com/neyslim')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('shows for an admin when the version changed since the last dismissal', async () => {
    state.serverPrefs = { kofi_seen_version: '2.241' }
    renderCard('2.242')
    expect(await screen.findByText('kofi.message')).toBeInTheDocument()
  })

  it('does not show for a non-admin', async () => {
    state.admin = false
    renderCard('2.242')
    await settle()
    expect(screen.queryByText('kofi.message')).not.toBeInTheDocument()
  })

  it('does not show again for the version already dismissed', async () => {
    state.serverPrefs = { kofi_seen_version: '2.242' }
    renderCard('2.242')
    await settle()
    await waitFor(() => expect(mocks.getPreferences).toHaveBeenCalled())
    await settle()
    expect(screen.queryByText('kofi.message')).not.toBeInTheDocument()
  })

  it('closing records the version, then stays hidden until the next version', async () => {
    const first = renderCard('2.242')
    fireEvent.click(await screen.findByRole('button', { name: 'kofi.dismiss' }))
    expect(mocks.persistPreference).toHaveBeenCalledWith('kofi_seen_version', '2.242')
    expect(screen.queryByText('kofi.message')).not.toBeInTheDocument()
    first.unmount()

    const again = renderCard('2.242')
    await settle()
    await settle()
    expect(screen.queryByText('kofi.message')).not.toBeInTheDocument()
    again.unmount()

    renderCard('2.243')
    expect(await screen.findByText('kofi.message')).toBeInTheDocument()
  })

  it('following the link records the version too', async () => {
    renderCard('2.242')
    fireEvent.click(await screen.findByRole('link', { name: 'kofi.support' }))
    expect(mocks.persistPreference).toHaveBeenCalledWith('kofi_seen_version', '2.242')
    expect(screen.queryByText('kofi.message')).not.toBeInTheDocument()
  })

  it('waits for an open dialog to close before showing', async () => {
    const dialog = document.createElement('div')
    dialog.setAttribute('role', 'dialog')
    dialog.setAttribute('data-state', 'open')
    dialog.setAttribute('data-test-dialog', '')
    document.body.appendChild(dialog)

    renderCard('2.242')
    await waitFor(() => expect(mocks.getPreferences).toHaveBeenCalled())
    await settle()
    expect(screen.queryByText('kofi.message')).not.toBeInTheDocument()

    await act(async () => { dialog.remove() })
    expect(await screen.findByText('kofi.message')).toBeInTheDocument()
  })

  it('does not show during the forced password change', async () => {
    state.auth = { ...state.auth, forcePasswordChange: true }
    renderCard('2.242')
    await waitFor(() => expect(mocks.getPreferences).toHaveBeenCalled())
    await settle()
    expect(screen.queryByText('kofi.message')).not.toBeInTheDocument()
  })
})
