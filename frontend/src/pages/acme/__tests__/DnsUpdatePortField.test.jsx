import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, opts) => (opts?.port !== undefined ? `${key}:${opts.port}` : key) }),
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

import DnsUpdatePortField from '../DnsUpdatePortField'
import { parseDnsUpdatePort, effectiveDnsUpdatePort } from '../dnsUpdatePort'

const renderField = (settings = {}, props = {}) => render(
  <DnsUpdatePortField clientSettings={{ dns_update_port: 0, ...settings }} canWrite value={String(settings.dns_update_port ?? 0)} onChange={vi.fn()} {...props} />,
)
const input = () => screen.getByRole('spinbutton', { name: 'acme.dnsUpdate.portLabel' })

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

describe('effectiveDnsUpdatePort', () => {
  it('uses the server effective port, and 0 when the field is missing or invalid', () => {
    expect(effectiveDnsUpdatePort({ dns_update_port: 8053, dns_update_port_env: '70000', dns_update_port_effective: 0 })).toBe(0)
    expect(effectiveDnsUpdatePort({ dns_update_port: 0, dns_update_port_env: '8053', dns_update_port_effective: 8053 })).toBe(8053)
    expect(effectiveDnsUpdatePort({ dns_update_port: 8053, dns_update_port_env: 5353 })).toBe(0)
    expect(effectiveDnsUpdatePort(undefined)).toBe(0)
  })
})

describe('DnsUpdatePortField', () => {
  it('is a field of the draft: no button of its own, the typed value handed to the page', () => {
    const onChange = vi.fn()
    renderField({}, { onChange })
    expect(screen.queryByRole('button')).toBeNull()
    fireEvent.change(input(), { target: { value: '8053' } })
    expect(onChange).toHaveBeenCalledWith('8053')
  })

  it('shows the error and the restart notice the page gives it', () => {
    renderField({}, { error: 'acme.dnsUpdate.portInvalid', restartRequired: true })
    expect(input()).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByText('acme.dnsUpdate.portInvalid')).toBeInTheDocument()
    expect(screen.getByText('acme.dnsUpdate.portRestartRequired')).toBeInTheDocument()
  })

  it('is read-only and shows the variable value when the environment overrides the port', () => {
    renderField({ dns_update_port: 8053, dns_update_port_env: 5353 })
    expect(input()).toHaveAttribute('readonly')
    expect(input()).toHaveValue(5353)
    expect(screen.getByText('acme.dnsUpdate.portEnvOverride:5353')).toBeInTheDocument()
  })

  it('does not repeat the card\'s description under the field, only the environment\'s override', () => {
    renderField({ dns_update_port: 8053 })
    expect(screen.queryByText('acme.dnsUpdate.portHelper')).toBeNull()
    expect(input()).not.toHaveAttribute('aria-describedby')
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

  it('shows disabled, not "not listening", when the variable is set but the effective port is 0', () => {
    renderField({ dns_update_port: 8053, dns_update_port_env: '70000', dns_update_port_effective: 0 })
    expect(screen.getByText('acme.dnsUpdate.portDisabled')).toBeInTheDocument()
    expect(screen.queryByText('acme.dnsUpdate.portNotListening')).not.toBeInTheDocument()
    expect(input()).toHaveValue(70000)
  })

  it('is disabled without write permission', () => {
    renderField({}, { canWrite: false })
    expect(input()).toBeDisabled()
  })
})
