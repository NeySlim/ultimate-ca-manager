/**
 * An administrator's view of another user's security keys.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

const m = vi.hoisted(() => ({
  getSecurityKeys: vi.fn(),
  deleteSecurityKey: vi.fn(),
  setSecurityKeyEnabled: vi.fn(),
  showConfirm: vi.fn(),
  showError: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key, i18n: { language: 'en' } }),
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../../services', () => ({
  usersService: {
    getSecurityKeys: m.getSecurityKeys,
    deleteSecurityKey: m.deleteSecurityKey,
    setSecurityKeyEnabled: m.setSecurityKeyEnabled,
  },
}))
vi.mock('../../contexts', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: m.showError, showConfirm: m.showConfirm }),
}))

import UserSecurityKeys from '../UserSecurityKeys'

const USER = { id: 7, username: 'alice' }
const KEY = { id: 3, name: 'YubiKey', enabled: true, created_at: '2026-10-01T00:00:00Z' }

function conflict() {
  return Object.assign(new Error('last factor'), { status: 409 })
}

describe('UserSecurityKeys', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    m.getSecurityKeys.mockResolvedValue({ data: [KEY] })
    m.deleteSecurityKey.mockResolvedValue({})
    m.setSecurityKeyEnabled.mockResolvedValue({})
    m.showConfirm.mockResolvedValue(true)
  })

  it("lists the user's keys", async () => {
    render(<UserSecurityKeys user={USER} />)
    expect(await screen.findByText('YubiKey')).toBeInTheDocument()
    expect(m.getSecurityKeys).toHaveBeenCalledWith(7)
  })

  it('removes a key after confirmation', async () => {
    render(<UserSecurityKeys user={USER} />)
    fireEvent.click(await screen.findByLabelText('common.delete'))
    await waitFor(() => expect(m.deleteSecurityKey).toHaveBeenCalledWith(7, 3, {}))
  })

  it('does nothing when the removal is cancelled', async () => {
    m.showConfirm.mockResolvedValue(false)
    render(<UserSecurityKeys user={USER} />)
    fireEvent.click(await screen.findByLabelText('common.delete'))
    await waitFor(() => expect(m.showConfirm).toHaveBeenCalled())
    expect(m.deleteSecurityKey).not.toHaveBeenCalled()
  })

  it('asks again for the last factor, then confirms it', async () => {
    m.deleteSecurityKey.mockRejectedValueOnce(conflict())
    render(<UserSecurityKeys user={USER} />)
    fireEvent.click(await screen.findByLabelText('common.delete'))
    await waitFor(() => expect(m.deleteSecurityKey).toHaveBeenLastCalledWith(7, 3, { confirmLastFactor: true }))
    expect(m.showConfirm).toHaveBeenCalledTimes(2)
    expect(m.showConfirm.mock.calls[1][0]).toBe('users.securityKeys.lastFactorConfirm')
  })

  it('keeps the last factor when the second question is declined', async () => {
    m.deleteSecurityKey.mockRejectedValueOnce(conflict())
    m.showConfirm.mockResolvedValueOnce(true).mockResolvedValueOnce(false)
    render(<UserSecurityKeys user={USER} />)
    fireEvent.click(await screen.findByLabelText('common.delete'))
    await waitFor(() => expect(m.showConfirm).toHaveBeenCalledTimes(2))
    expect(m.deleteSecurityKey).toHaveBeenCalledTimes(1)
  })

  it('disables an enabled key', async () => {
    render(<UserSecurityKeys user={USER} />)
    fireEvent.click(await screen.findByText('common.disable'))
    await waitFor(() => expect(m.setSecurityKeyEnabled).toHaveBeenCalledWith(7, 3, false, {}))
  })

  it('reports other errors without asking again', async () => {
    m.deleteSecurityKey.mockRejectedValueOnce(Object.assign(new Error('boom'), { status: 500 }))
    render(<UserSecurityKeys user={USER} />)
    fireEvent.click(await screen.findByLabelText('common.delete'))
    await waitFor(() => expect(m.showError).toHaveBeenCalledWith('boom'))
    expect(m.showConfirm).toHaveBeenCalledTimes(1)
  })
})
