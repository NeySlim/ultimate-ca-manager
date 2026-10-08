/**
 * Remote syslog over TCP could not be chosen (#380): the handlers read
 * `e.target.value` while Select hands over the chosen value itself.
 */
import { describe, expect, it, vi } from 'vitest'
import { useState } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

// Same contract as components/Select: onChange receives the value, not an event
vi.mock('../../../components', () => ({
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Input: ({ label }) => <label>{label}</label>,
  Select: ({ label, value, options, onChange }) => (
    <select aria-label={label} value={value} onChange={(e) => onChange(e.target.value)}>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  ),
  DetailHeader: ({ title }) => <header>{title}</header>,
  DetailSection: ({ title, children }) => <section><h2>{title}</h2>{children}</section>,
  DetailContent: ({ children }) => <div>{children}</div>,
}))

vi.mock('../../../components/ui/ToggleSwitch', () => ({
  ToggleSwitch: ({ label, checked, onChange }) => (
    <input type="checkbox" aria-label={label} checked={!!checked} onChange={(e) => onChange(e.target.checked)} />
  ),
}))

import AuditSection from '../AuditSection'

let latest
function Harness() {
  const [syslogConfig, setSyslogConfig] = useState({
    enabled: true, host: 'logs.example.test', port: 514, protocol: 'udp',
    tls: false, tls_verify: true, framing: 'line', categories: [],
  })
  latest = syslogConfig
  return (
    <AuditSection
      settings={{ audit_enabled: true }} updateSetting={vi.fn()} handleSave={vi.fn()} saving={false}
      hasPermission={() => true} syslogConfig={syslogConfig}
      updateSyslogConfig={(key, value) => setSyslogConfig((prev) => ({ ...prev, [key]: value }))}
      syslogSaving={false} syslogTesting={false} handleSaveSyslog={vi.fn()} handleTestSyslog={vi.fn()}
    />
  )
}

describe('AuditSection remote syslog protocol (#380)', () => {
  it('switches to TCP and offers TLS and framing', () => {
    render(<Harness />)
    fireEvent.change(screen.getByLabelText('settings.syslogProtocol'), { target: { value: 'tcp' } })
    expect(latest.protocol).toBe('tcp')
    expect(screen.getByLabelText('settings.syslogTls')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('settings.syslogFraming'), { target: { value: 'octet' } })
    expect(latest.framing).toBe('octet')
  })
})
