/**
 * The audit log cannot be switched off or filtered by event from the UI: the
 * former switch and checkboxes were stored nowhere and changed nothing.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

vi.mock('../../../components', () => ({
  Select: () => null,
  Button: ({ children, loading: _loading, ...props }) => <button {...props}>{children}</button>,
  Input: ({ label, helperText: _helperText, ...props }) => <input aria-label={label} {...props} />,
  DetailHeader: ({ title }) => <header>{title}</header>,
  DetailSection: ({ title, children }) => <section><h2>{title}</h2>{children}</section>,
  DetailContent: ({ children }) => <div>{children}</div>,
}))
vi.mock('../../../components/ui/ToggleSwitch', () => ({ ToggleSwitch: ({ label }) => <span>{label}</span> }))

import AuditSection from '../AuditSection'

describe('AuditSection offers only what the backend applies', () => {
  it('has no on/off switch and no per-event checkboxes, and keeps the retention save', () => {
    render(
      <AuditSection
        settings={{}}
        updateSetting={vi.fn()}
        handleSave={vi.fn()}
        saving={false}
        hasPermission={() => true}
        syslogConfig={{ enabled: false, host: '', port: 514, categories: [] }}
        updateSyslogConfig={vi.fn()}
        syslogSaving={false}
        syslogTesting={false}
        handleSaveSyslog={vi.fn()}
        handleTestSyslog={vi.fn()}
      />
    )
    expect(screen.queryByText('settings.enableAuditLogging')).toBeNull()
    expect(screen.queryByText('settings.eventsToLog')).toBeNull()
    expect(screen.queryByText('settings.eventUserLoginLogout')).toBeNull()
    expect(screen.getByLabelText('settings.logRetention')).toBeTruthy()
    expect(screen.getAllByText('common.saveChanges').length).toBeGreaterThan(0)
  })
})
