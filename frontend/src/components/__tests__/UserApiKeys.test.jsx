/**
 * An administrator's view of another user's API keys.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

const m = vi.hoisted(() => ({
  getApiKeys: vi.fn(),
  deleteApiKey: vi.fn(),
  showConfirm: vi.fn(),
  showSuccess: vi.fn(),
  showError: vi.fn(),
  t: (key) => key,
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: m.t, i18n: { language: 'en' } }),
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../../services', () => ({
  usersService: { getApiKeys: m.getApiKeys, deleteApiKey: m.deleteApiKey },
}))
vi.mock('../../contexts', () => ({
  useNotification: () => ({ showSuccess: m.showSuccess, showError: m.showError, showConfirm: m.showConfirm }),
}))

import UserApiKeys from '../UserApiKeys'

const USER = { id: 7, username: 'alice' }
const ACTIVE = { id: 3, name: 'ci-runner', key_prefix: 'ucm_ak_AbC1', is_active: true, is_expired: false,
  expires_at: '2027-10-01T00:00:00Z', last_used_at: null }
const REVOKED = { ...ACTIVE, id: 4, name: 'old-script', is_active: false }

describe('UserApiKeys', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    m.getApiKeys.mockResolvedValue({ data: [ACTIVE] })
    m.deleteApiKey.mockResolvedValue({})
    m.showConfirm.mockResolvedValue(true)
  })

  it("lists the user's keys with their prefix", async () => {
    render(<UserApiKeys user={USER} />)
    expect(await screen.findByText('ci-runner')).toBeInTheDocument()
    expect(screen.getByText('ucm_ak_AbC1…')).toBeInTheDocument()
    expect(m.getApiKeys).toHaveBeenCalledWith(7)
  })

  it('revokes an active key after confirmation, then reloads', async () => {
    render(<UserApiKeys user={USER} />)
    fireEvent.click(await screen.findByLabelText('common.revoke'))
    await waitFor(() => expect(m.deleteApiKey).toHaveBeenCalledWith(7, 3))
    expect(m.showConfirm.mock.calls[0][0]).toBe('users.apiKeys.revokeConfirm')
    expect(m.showSuccess).toHaveBeenCalledWith('users.apiKeys.revoked')
    await waitFor(() => expect(m.getApiKeys).toHaveBeenCalledTimes(2))
  })

  it('offers deletion for a revoked key', async () => {
    m.getApiKeys.mockResolvedValue({ data: [REVOKED] })
    render(<UserApiKeys user={USER} />)
    fireEvent.click(await screen.findByLabelText('common.delete'))
    await waitFor(() => expect(m.deleteApiKey).toHaveBeenCalledWith(7, 4))
    expect(m.showConfirm.mock.calls[0][0]).toBe('users.apiKeys.deleteConfirm')
    expect(m.showSuccess).toHaveBeenCalledWith('users.apiKeys.deleted')
  })

  it('does nothing when the confirmation is cancelled', async () => {
    m.showConfirm.mockResolvedValue(false)
    render(<UserApiKeys user={USER} />)
    fireEvent.click(await screen.findByLabelText('common.revoke'))
    await waitFor(() => expect(m.showConfirm).toHaveBeenCalled())
    expect(m.deleteApiKey).not.toHaveBeenCalled()
  })

  it('reports a load failure', async () => {
    m.getApiKeys.mockRejectedValue(new Error('boom'))
    render(<UserApiKeys user={USER} />)
    await waitFor(() => expect(m.showError).toHaveBeenCalledWith('boom'))
    expect(screen.getByText('users.apiKeys.none')).toBeInTheDocument()
  })
})
