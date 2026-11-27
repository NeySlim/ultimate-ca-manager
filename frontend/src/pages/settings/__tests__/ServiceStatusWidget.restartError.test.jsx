/** Restart Service: a refused restart says the server's reason, the generic text only without one. */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { act, render, screen, waitFor } from '@testing-library/react'

const m = vi.hoisted(() => ({ showError: vi.fn(), restartService: vi.fn() }))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key, i18n: { language: 'en' } }),
}))
vi.mock('../../../services', () => ({
  systemService: {
    getServiceStatus: () => Promise.resolve({ data: { version: '3.1', pid: 1, is_docker: false } }),
    restartService: m.restartService,
  },
}))
vi.mock('../../../contexts', () => ({
  useNotification: () => ({ showError: m.showError, showConfirm: () => Promise.resolve(true) }),
}))
vi.mock('../../../hooks', () => ({
  usePermission: () => ({ canWrite: () => true }),
  useServiceReconnect: () => ({ reconnecting: false, waitForRestart: vi.fn(), cancel: vi.fn() }),
}))
vi.mock('../../../components', () => ({ ServiceReconnectOverlay: () => null }))

import ServiceStatusWidget from '../ServiceStatusWidget'

describe('ServiceStatusWidget restart failure', () => {
  beforeEach(() => vi.clearAllMocks())

  it('gives the server reason', async () => {
    m.restartService.mockRejectedValue(Object.assign(new Error('Restart is disabled in HA'), { status: 409 }))
    render(<ServiceStatusWidget />)
    const restart = await screen.findByText('settings.restartService')
    await act(async () => { restart.click() })
    await waitFor(() => expect(m.showError).toHaveBeenCalledWith('Restart is disabled in HA'))
  })

  it('falls back to the generic text without one', async () => {
    m.restartService.mockRejectedValue(new Error(''))
    render(<ServiceStatusWidget />)
    const restart = await screen.findByText('settings.restartService')
    await act(async () => { restart.click() })
    await waitFor(() => expect(m.showError).toHaveBeenCalledWith('settings.restartFailed'))
  })
})
