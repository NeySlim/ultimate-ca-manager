/**
 * #380: the Select wrapper calls onChange with the option's value, so a
 * handler reading e.target.value threw and TCP could not be chosen.
 * Uses the real Radix-backed Select; jsdom needs the polyfills below.
 */
import { describe, it, expect, vi, beforeAll } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

vi.mock('../../../components', async () => {
  const { SelectComponent } = await vi.importActual('../../../components/Select')
  return {
    Select: SelectComponent,
    Button: ({ children, loading: _loading, ...props }) => <button {...props}>{children}</button>,
    Input: () => <input />,
    DetailHeader: ({ title }) => <header>{title}</header>,
    DetailSection: ({ children }) => <section>{children}</section>,
    DetailContent: ({ children }) => <div>{children}</div>,
  }
})
vi.mock('../../../components/ui/ToggleSwitch', () => ({ ToggleSwitch: () => <input type="checkbox" /> }))

import AuditSection from '../AuditSection'

beforeAll(() => {
  global.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture || (() => false)
  Element.prototype.setPointerCapture = Element.prototype.setPointerCapture || (() => {})
  Element.prototype.releasePointerCapture = Element.prototype.releasePointerCapture || (() => {})
  Element.prototype.scrollIntoView = Element.prototype.scrollIntoView || (() => {})
})

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
  it('selecting TCP sets the protocol', async () => {
    const user = userEvent.setup()
    const updateSyslogConfig = vi.fn()
    renderAudit({ protocol: 'udp' }, updateSyslogConfig)
    await user.click(screen.getByRole('combobox'))
    await user.click(await screen.findByRole('option', { name: 'TCP' }))
    expect(updateSyslogConfig).toHaveBeenCalledWith('protocol', 'tcp')
  })

  it('selecting octet counting sets the framing', async () => {
    const user = userEvent.setup()
    const updateSyslogConfig = vi.fn()
    renderAudit({ protocol: 'tcp', framing: 'line' }, updateSyslogConfig)
    const framing = screen.getAllByRole('combobox')[1]
    await user.click(framing)
    await user.click(await screen.findByRole('option', { name: 'settings.syslogFramingOctet' }))
    expect(updateSyslogConfig).toHaveBeenCalledWith('framing', 'octet')
  })
})
