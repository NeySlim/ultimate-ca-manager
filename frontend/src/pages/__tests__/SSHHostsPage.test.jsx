/**
 * SSH Hosts (#451): hosts with their certificate state, renewal and KRL pull; revoke and pause
 * follow write:ssh; an enrollment token is shown once, with the command that carries it.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const authState = vi.hoisted(() => ({ permissions: [] }))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, o) => (o && o.action ? `${o.action} ${o.name}` : key),
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

const notify = vi.hoisted(() => ({
  showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn(),
  showConfirm: vi.fn(() => Promise.resolve(true)),
}))

vi.mock('../../contexts', () => ({
  useNotification: () => notify,
  useMobile: () => ({ isMobile: false, isTablet: false, sidebarOpen: true, setSidebarOpen: vi.fn() }),
}))
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ permissions: authState.permissions }),
}))

const svc = vi.hoisted(() => ({
  getAll: vi.fn(), getTokens: vi.fn(), revoke: vi.fn(), setAutoRenew: vi.fn(), createToken: vi.fn(), revokeToken: vi.fn(), cas: vi.fn(),
}))
vi.mock('../../services', () => ({
  sshHostsService: {
    getAll: (...a) => svc.getAll(...a), getTokens: (...a) => svc.getTokens(...a), revoke: (...a) => svc.revoke(...a),
    setAutoRenew: (...a) => svc.setAutoRenew(...a), createToken: (...a) => svc.createToken(...a), revokeToken: (...a) => svc.revokeToken(...a),
  },
  sshCasService: { getAll: (...a) => svc.cas(...a) },
}))

import SSHHostsPage from '../SSHHostsPage'

const HOST = {
  id: 7, refid: 'h-7', name: 'web01.example.com', principals: ['web01.example.com', 'web01'], state: 'valid', auto_renew: true,
  ca_name: 'Hosts', valid_to: '2027-01-01T00:00:00Z', last_krl_sync_at: null, renew_percent: 30, key_type: 'ssh-ed25519',
}
const HOST_CA = { id: 3, refid: 'ca-host-3', name: 'Hosts', ca_type: 'host' }

function renderPage(permissions, path = '/ssh/hosts') {
  authState.permissions = permissions
  return render(<MemoryRouter initialEntries={[path]}><SSHHostsPage /></MemoryRouter>)
}

describe('SSHHostsPage', () => {
  beforeEach(() => {
    window.localStorage.clear()
    Object.values(svc).forEach((f) => f.mockReset())
    notify.showConfirm.mockClear()
    svc.getAll.mockResolvedValue({ data: [HOST], meta: { total: 1, counts: { valid: 1, expired: 0, revoked: 0, total: 1 } } })
    svc.getTokens.mockResolvedValue({ data: [] })
    svc.cas.mockResolvedValue({ data: [HOST_CA, { id: 4, refid: 'u', name: 'Users', ca_type: 'user' }] })
  })

  it('lists the host with its renewal and state, and no write action on read:ssh alone', async () => {
    renderPage(['read:ssh', 'read:ssh_cas'])
    expect((await screen.findAllByText('web01.example.com')).length).toBeGreaterThan(0)
    expect(screen.getAllByText('sshHosts.renewalOn').length).toBeGreaterThan(0)
    expect(screen.getAllByText('sshHosts.stateValid').length).toBeGreaterThan(0)
    expect(screen.queryAllByLabelText(/sshHosts.revokeHost/)).toHaveLength(0)
    expect(screen.queryAllByText('sshHosts.token.create')).toHaveLength(0)
  })

  it('revokes the host after confirmation and pauses its renewal', async () => {
    svc.revoke.mockResolvedValue({ data: { ...HOST, state: 'revoked' } })
    svc.setAutoRenew.mockResolvedValue({ data: { ...HOST, auto_renew: false } })
    renderPage(['read:ssh', 'write:ssh', 'read:ssh_cas'])
    await screen.findAllByText('web01.example.com')
    fireEvent.click(screen.getAllByLabelText(/sshHosts.revokeHost/)[0])
    await waitFor(() => expect(svc.revoke).toHaveBeenCalledWith(7))
    expect(notify.showConfirm).toHaveBeenCalled()
    fireEvent.click(screen.getAllByLabelText(/sshHosts.pauseRenewal/)[0])
    await waitFor(() => expect(svc.setAutoRenew).toHaveBeenCalledWith(7, false))
  })

  it('does not revoke when the confirmation is declined', async () => {
    notify.showConfirm.mockResolvedValueOnce(false)
    renderPage(['read:ssh', 'write:ssh'])
    await screen.findAllByText('web01.example.com')
    fireEvent.click(screen.getAllByLabelText(/sshHosts.revokeHost/)[0])
    await waitFor(() => expect(notify.showConfirm).toHaveBeenCalled())
    expect(svc.revoke).not.toHaveBeenCalled()
  })

  it('creates a token for a host CA only, then shows it once with its command', async () => {
    svc.createToken.mockResolvedValue({ data: { id: 1, token: 'ucmh_secretvalue', token_prefix: 'ucmh_sec', expires_at: '2026-12-01T00:00:00Z' } })
    renderPage(['read:ssh', 'write:ssh', 'read:ssh_cas'])
    await screen.findAllByText('web01.example.com')
    fireEvent.click(screen.getAllByText('sshHosts.token.create')[0])
    const dialog = await screen.findByRole('dialog')
    const ca = within(dialog).getByLabelText('sshHosts.token.hostCa')
    expect([...ca.options].filter((o) => !o.disabled).map((o) => o.textContent)).toEqual(['Hosts'])
    fireEvent.change(within(dialog).getByLabelText('sshHosts.token.principals'), { target: { value: 'web02.example.com, web02' } })
    fireEvent.submit(dialog.querySelector('form'))
    await waitFor(() => expect(svc.createToken).toHaveBeenCalledWith({
      ca_id: 3, principals: ['web02.example.com', 'web02'], lifetime_seconds: 3600, renew_percent: 30,
    }))
    expect(await within(dialog).findByTestId('ssh-token-secret')).toHaveTextContent('ucmh_secretvalue')
    // The token travels in sudo's environment, never in the URL nor in an argument ps shows
    const command = within(dialog).getByTestId('ssh-token-command').textContent
    expect(command).toContain('/ssh/setup/ca-host-3/agent')
    expect(command).toContain('| UCM_ENROLL_TOKEN=ucmh_secretvalue sudo --preserve-env=UCM_ENROLL_TOKEN sh')
    expect(command.split('|')[0]).not.toContain('ucmh_secretvalue')
    fireEvent.click(within(dialog).getByText('common.close'))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(screen.queryByText('ucmh_secretvalue')).toBeNull()
  })

  it('keeps the token dialog open while the token is created, so its single showing is not lost', async () => {
    let answer
    svc.createToken.mockImplementation(() => new Promise((resolve) => { answer = resolve }))
    renderPage(['read:ssh', 'write:ssh', 'read:ssh_cas'])
    await screen.findAllByText('web01.example.com')
    fireEvent.click(screen.getAllByText('sshHosts.token.create')[0])
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText('sshHosts.token.principals'), { target: { value: 'web02' } })
    const form = dialog.querySelector('form')
    fireEvent.submit(form)
    fireEvent.submit(form)
    await waitFor(() => expect(svc.createToken).toHaveBeenCalledTimes(1))
    fireEvent.keyDown(dialog, { key: 'Escape' })
    fireEvent.click(within(dialog).getByLabelText('common.closeWindow'))
    fireEvent.click(within(dialog).getByText('common.cancel'))
    expect(screen.getByRole('dialog')).toBe(dialog)
    answer({ data: { id: 2, token: 'ucmh_kept', token_prefix: 'ucmh_kep', expires_at: '2026-12-01T00:00:00Z' } })
    expect(await within(dialog).findByTestId('ssh-token-secret')).toHaveTextContent('ucmh_kept')
    expect(svc.createToken).toHaveBeenCalledTimes(1)
    fireEvent.keyDown(dialog, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })

  it('cancels the token form without sending it, and opens it empty the next time', async () => {
    renderPage(['read:ssh', 'write:ssh', 'read:ssh_cas'])
    await screen.findAllByText('web01.example.com')
    fireEvent.click(screen.getAllByText('sshHosts.token.create')[0])
    let dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText('sshHosts.token.principals'), { target: { value: 'web02' } })
    fireEvent.change(within(dialog).getByLabelText('common.description'), { target: { value: 'left over' } })
    fireEvent.click(within(dialog).getByText('common.cancel'))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(svc.createToken).not.toHaveBeenCalled()
    fireEvent.click(screen.getAllByText('sshHosts.token.create')[0])
    dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByLabelText('sshHosts.token.principals')).toHaveValue('')
    expect(within(dialog).getByLabelText('common.description')).toHaveValue('')
    expect(within(dialog).getByLabelText('sshHosts.token.renewPercent')).toHaveValue(30)
  })

  it('lists the tokens and revokes an active one', async () => {
    svc.getTokens.mockResolvedValue({ data: [
      { id: 5, token_prefix: 'ucmh_aaa', state: 'active', principals: ['a'], expires_at: '2026-12-01T00:00:00Z' },
      { id: 6, token_prefix: 'ucmh_bbb', state: 'used', principals: ['b'], expires_at: '2026-12-01T00:00:00Z' },
    ] })
    svc.revokeToken.mockResolvedValue({ data: {} })
    renderPage(['read:ssh', 'write:ssh'], '/ssh/hosts?view=tokens')
    expect((await screen.findAllByText('sshHosts.token.state.used')).length).toBeGreaterThan(0)
    const revokes = screen.getAllByLabelText(/sshHosts.token.revoke/)
    expect(revokes).toHaveLength(1)
    fireEvent.click(revokes[0])
    await waitFor(() => expect(svc.revokeToken).toHaveBeenCalledWith(5))
  })
})
