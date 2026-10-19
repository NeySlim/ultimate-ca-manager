/**
 * Settings > General: no "ACME public TLS certificate" selector. The id was
 * stored as metadata and never applied to any listener or deployment.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

vi.mock('../../../components', () => ({
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Input: ({ label }) => <label>{label}<input /></label>,
  Select: ({ label }) => <label>{label}<select /></label>,
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

const getAll = vi.fn().mockResolvedValue({ data: [] })
vi.mock('../../../services', () => ({
  certificatesService: { getAll: (...a) => getAll(...a) },
  settingsService: { updateBulk: vi.fn() },
}))

import GeneralSection from '../GeneralSection'

describe('ACME public vhost settings', () => {
  it('offer no TLS certificate selector and fetch no certificates', () => {
    render(
      <GeneralSection settings={{}} updateSetting={vi.fn()} handleSave={vi.fn()} saving={false}
        canWrite={() => true} hasPermission={() => true} />
    )
    expect(screen.getByText('settings.acmePublicVhost')).toBeInTheDocument()
    expect(screen.queryByText('settings.acmePublicTlsCertId')).toBeNull()
    expect(getAll).not.toHaveBeenCalled()
  })
})
