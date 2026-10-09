/**
 * Audit retention: the field shows 0 (keep every log) when nothing is stored,
 * is editable by settings admins only, and sends a number.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

vi.mock('../../../components', () => ({
  Select: () => null,
  Button: ({ children, loading: _loading, ...props }) => <button {...props}>{children}</button>,
  Input: ({ label, helperText: _helperText, ...props }) => <input aria-label={label} {...props} />,
  DetailHeader: ({ title }) => <header>{title}</header>,
  DetailSection: ({ children }) => <section>{children}</section>,
  DetailContent: ({ children }) => <div>{children}</div>,
}))
vi.mock('../../../components/ui/ToggleSwitch', () => ({ ToggleSwitch: () => <input type="checkbox" /> }))

import AuditSection from '../AuditSection'

const renderAudit = (settings, updateSetting = vi.fn(), granted = () => true) => {
  render(
    <AuditSection
      settings={settings}
      updateSetting={updateSetting}
      handleSave={vi.fn()}
      saving={false}
      hasPermission={granted}
      syslogConfig={{ enabled: false, host: '', port: 514, categories: [] }}
      updateSyslogConfig={vi.fn()}
      syslogSaving={false}
      syslogTesting={false}
      handleSaveSyslog={vi.fn()}
      handleTestSyslog={vi.fn()}
    />
  )
  return screen.getByLabelText('settings.logRetention')
}

describe('AuditSection audit retention', () => {
  it('shows 0 when no retention is stored, and is editable', () => {
    const field = renderAudit({})
    expect(field.value).toBe('0')
    expect(field.disabled).toBe(false)
  })

  it('shows the stored retention', () => {
    expect(renderAudit({ audit_retention_days: 365 }).value).toBe('365')
  })

  it('sends a number, and 0 for an emptied field', () => {
    const updateSetting = vi.fn()
    const field = renderAudit({ audit_retention_days: 365 }, updateSetting)
    fireEvent.change(field, { target: { value: '400' } })
    expect(updateSetting).toHaveBeenLastCalledWith('audit_retention_days', 400)
    fireEvent.change(field, { target: { value: '' } })
    expect(updateSetting).toHaveBeenLastCalledWith('audit_retention_days', 0)
  })

  it('is read-only without admin:settings, as the backend refuses it', () => {
    expect(renderAudit({}, vi.fn(), (p) => p !== 'admin:settings').disabled).toBe(true)
  })
})
