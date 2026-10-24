import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, opts) => (opts?.port !== undefined ? `${key}:${opts.port}` : key) }),
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

import DnsUpdatePortField from '../DnsUpdatePortField'
import { parseDnsUpdatePort } from '../dnsUpdatePort'

const onSave = vi.fn()
const renderField = (settings = {}, props = {}) => render(
  <DnsUpdatePortField clientSettings={{ dns_update_port: 0, ...settings }} canWrite onSave={onSave} {...props} />,
)
const input = () => screen.getByRole('spinbutton', { name: 'acme.dnsUpdate.portLabel' })
const typePort = async (user, value) => {
  await user.clear(input())
  await user.type(input(), value)
}
const save = (user) => user.click(screen.getByRole('button', { name: 'common.save' }))

describe('parseDnsUpdatePort', () => {
  it('accepts 0 and 1024 to 65535', () => {
    expect(parseDnsUpdatePort('0')).toBe(0)
    expect(parseDnsUpdatePort('1024')).toBe(1024)
    expect(parseDnsUpdatePort('8053')).toBe(8053)
    expect(parseDnsUpdatePort('65535')).toBe(65535)
  })

  it('rejects the rest', () => {
    for (const bad of ['53', '1023', '65536', '70000', '-1', '', 'abc', '80.5']) {
      expect(parseDnsUpdatePort(bad), bad).toBeNull()
    }
  })
})

describe('DnsUpdatePortField', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    onSave.mockResolvedValue({ data: { restart_required: true } })
  })

  it('rejects ports 53 and 70000 without calling the server', async () => {
    const user = userEvent.setup()
    renderField()
    for (const bad of ['53', '70000']) {
      await typePort(user, bad)
      await save(user)
      expect(await screen.findByText('acme.dnsUpdate.portInvalid')).toBeInTheDocument()
    }
    expect(onSave).not.toHaveBeenCalled()
  })

  it('saves 8053 and asks for a restart', async () => {
    const user = userEvent.setup()
    renderField()
    await typePort(user, '8053')
    await save(user)
    await waitFor(() => expect(onSave).toHaveBeenCalledWith(8053))
    expect(await screen.findByText('acme.dnsUpdate.portRestartRequired')).toBeInTheDocument()
    expect(screen.queryByText('acme.dnsUpdate.portInvalid')).not.toBeInTheDocument()
  })

  it('saves 0 to disable the listener', async () => {
    const user = userEvent.setup()
    renderField({ dns_update_port: 8053 })
    await typePort(user, '0')
    await save(user)
    await waitFor(() => expect(onSave).toHaveBeenCalledWith(0))
  })

  it('shows no restart notice when the server does not ask for one', async () => {
    const user = userEvent.setup()
    onSave.mockResolvedValue({ data: null })
    renderField()
    await typePort(user, '8053')
    await save(user)
    await waitFor(() => expect(onSave).toHaveBeenCalled())
    expect(screen.queryByText('acme.dnsUpdate.portRestartRequired')).not.toBeInTheDocument()
  })

  it('is read-only and shows the variable value when the environment overrides the port', () => {
    renderField({ dns_update_port: 8053, dns_update_port_env: 5353 })
    expect(input()).toHaveAttribute('readonly')
    expect(input()).toHaveValue(5353)
    expect(screen.getByText('acme.dnsUpdate.portEnvOverride:5353')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'common.save' })).not.toBeInTheDocument()
  })

  it('shows the listening status', () => {
    renderField({ dns_update_port: 8053, dns_update_listening: true })
    expect(screen.getByText('acme.dnsUpdate.portListening')).toBeInTheDocument()
  })

  it('shows disabled, or "not listening" when a port waits for a restart', () => {
    const { unmount } = renderField({ dns_update_port: 0 })
    expect(screen.getByText('acme.dnsUpdate.portDisabled')).toBeInTheDocument()
    unmount()
    renderField({ dns_update_port: 8053, dns_update_listening: false })
    expect(screen.getByText('acme.dnsUpdate.portNotListening')).toBeInTheDocument()
  })

  it('has no save button without write permission', () => {
    renderField({}, { canWrite: false })
    expect(screen.queryByRole('button', { name: 'common.save' })).not.toBeInTheDocument()
    expect(input()).toBeDisabled()
  })
})
