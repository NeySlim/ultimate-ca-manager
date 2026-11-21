/**
 * #380: the select hands the option's value to the section, so TCP can be chosen; the
 * mockup's transport (TLS, TCP, UDP) maps TLS to TCP with TLS on.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

import AuditSection from '../AuditSection'

const renderAudit = (syslogConfig, updateSyslogConfig) => render(
  <AuditSection
    settings={{}}
    updateSetting={vi.fn()}
    handleSave={vi.fn()}
    saving={false}
    hasPermission={() => true}
    syslogConfig={{ enabled: true, host: 'syslog.example.com', port: 514, categories: [], ...syslogConfig }}
    updateSyslogConfig={updateSyslogConfig}
    syslogSaving={false}
    syslogTesting={false}
    handleSaveSyslog={vi.fn()}
    handleTestSyslog={vi.fn()}
  />
)

describe('AuditSection remote syslog selects (#380)', () => {
  it('selecting TCP sets the protocol, TLS off', async () => {
    const user = userEvent.setup()
    const updateSyslogConfig = vi.fn()
    renderAudit({ protocol: 'udp' }, updateSyslogConfig)
    await user.selectOptions(screen.getByLabelText('settings.syslogProtocol'), 'TCP')
    expect(updateSyslogConfig).toHaveBeenCalledWith('protocol', 'tcp')
    expect(updateSyslogConfig).toHaveBeenCalledWith('tls', false)
  })

  it('offers the mockup transports, TLS being TCP with TLS on', async () => {
    const user = userEvent.setup()
    const updateSyslogConfig = vi.fn()
    renderAudit({ protocol: 'udp' }, updateSyslogConfig)
    const transport = screen.getByLabelText('settings.syslogProtocol')
    expect([...transport.options].map((o) => o.value)).toEqual(['tls', 'tcp', 'udp'])
    expect(transport.value).toBe('udp')
    await user.selectOptions(transport, 'settings.syslogTransportTls')
    expect(updateSyslogConfig).toHaveBeenCalledWith('protocol', 'tcp')
    expect(updateSyslogConfig).toHaveBeenCalledWith('tls', true)
  })

  it('shows a stored TCP with TLS as TLS, with its certificate check', () => {
    renderAudit({ protocol: 'tcp', tls: true, tls_verify: false }, vi.fn())
    expect(screen.getByLabelText('settings.syslogProtocol').value).toBe('tls')
    expect(screen.getByRole('checkbox', { name: 'settings.syslogTlsVerify' }).checked).toBe(false)
    expect(screen.getByRole('alert')).toHaveTextContent('settings.syslogTlsVerifyWarning')
  })

  it('selecting octet counting sets the framing', async () => {
    const user = userEvent.setup()
    const updateSyslogConfig = vi.fn()
    renderAudit({ protocol: 'tcp', framing: 'line' }, updateSyslogConfig)
    await user.selectOptions(screen.getByLabelText('settings.syslogFraming'), 'settings.syslogFramingOctet')
    expect(updateSyslogConfig).toHaveBeenCalledWith('framing', 'octet')
  })

  it('has no framing over UDP', () => {
    renderAudit({ protocol: 'udp' }, vi.fn())
    expect(screen.queryByLabelText('settings.syslogFraming')).toBeNull()
  })

  it('toggles a category as a pressed button', async () => {
    const user = userEvent.setup()
    const updateSyslogConfig = vi.fn()
    renderAudit({ protocol: 'udp', categories: ['ca'] }, updateSyslogConfig)
    expect(screen.getByRole('button', { name: 'settings.syslogCatCAs' })).toHaveAttribute('aria-pressed', 'true')
    await user.click(screen.getByRole('button', { name: 'ACME' }))
    expect(updateSyslogConfig).toHaveBeenCalledWith('categories', ['ca', 'acme'])
    await user.click(screen.getByRole('button', { name: 'settings.syslogCatCAs' }))
    expect(updateSyslogConfig).toHaveBeenLastCalledWith('categories', [])
  })
})
