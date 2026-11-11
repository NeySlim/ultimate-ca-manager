import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

vi.mock('../../../components', () => ({
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Input: ({ label, disabled, helperText }) => (
    <label>
      <span>{label}</span>
      <input aria-label={typeof label === 'string' ? label : undefined} disabled={disabled} readOnly />
      <small>{helperText}</small>
    </label>
  ),
  Select: () => <select />,
  Badge: ({ children }) => <span>{children}</span>,
  DetailHeader: ({ title }) => <header>{title}</header>,
  DetailSection: ({ children }) => <section>{children}</section>,
  DetailGrid: ({ children }) => <div>{children}</div>,
  DetailContent: ({ children }) => <div>{children}</div>,
}))
vi.mock('../../../components/ui/ToggleSwitch', () => ({ ToggleSwitch: () => <input type="checkbox" /> }))
vi.mock('../../../contexts', () => ({ useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn() }) }))
vi.mock('../ServiceStatusWidget', () => ({ default: () => null }))
vi.mock('../PublicEndpointsPanel', () => ({ default: () => null }))
vi.mock('../../../services', () => ({
  certificatesService: { getAll: () => Promise.resolve({ data: [] }) },
  settingsService: { updateBulk: vi.fn() },
}))

import GeneralSection from '../GeneralSection'

const renderWith = (settings) => render(
  <GeneralSection settings={settings} updateSetting={vi.fn()} handleSave={vi.fn()} saving={false}
    canWrite={() => true} hasPermission={() => true} />
)

describe('HTTP protocol port pinned by the environment', () => {
  it('is read-only and says where it is set', () => {
    renderWith({ http_protocol_port: 9090, env_locked: { http_protocol_port_env: true } })
    expect(screen.getByLabelText('settings.httpProtocolPort')).toBeDisabled()
    expect(screen.getByText('settings.httpProtocolPortEnvLocked')).toBeInTheDocument()
  })

  it('stays editable when the environment leaves it alone', () => {
    renderWith({ http_protocol_port: 8080, env_locked: { http_protocol_port_env: false } })
    expect(screen.getByLabelText('settings.httpProtocolPort')).not.toBeDisabled()
    expect(screen.queryByText('settings.httpProtocolPortEnvLocked')).toBeNull()
  })
})
