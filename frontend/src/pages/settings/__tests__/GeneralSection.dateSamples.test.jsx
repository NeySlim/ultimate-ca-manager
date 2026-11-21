/**
 * Date format choices of General, their samples in the interface language.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key, i18n: { language: 'fr' } }),
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
  Select: ({ label, options = [] }) => <select aria-label={label}>{options.map((o) => <option key={o.value}>{o.label}</option>)}</select>,
  Badge: ({ children }) => <span>{children}</span>,
  DetailHeader: ({ title }) => <header>{title}</header>,
  DetailSection: ({ children }) => <section>{children}</section>,
  DetailGrid: ({ children }) => <div>{children}</div>,
  DetailContent: ({ children }) => <div>{children}</div>,
}))
vi.mock('../../../contexts', () => ({ useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn() }) }))
vi.mock('../ServiceStatusWidget', () => ({ default: () => null }))
vi.mock('../PublicEndpointsPanel', () => ({ default: () => null }))
vi.mock('../../../services', () => ({
  certificatesService: { getAll: () => Promise.resolve({ data: [] }) },
  settingsService: { updateBulk: vi.fn() },
}))

import GeneralSection from '../GeneralSection'

// The date format samples read in the interface language, not in English
describe('date format samples', () => {
  it('writes the short and long samples in the reader language', () => {
    render(<GeneralSection settings={{}} updateSetting={vi.fn()} handleSave={vi.fn()} saving={false}
      canWrite={() => true} hasPermission={() => true} />)
    const options = [...screen.getByLabelText('settings.dateFormat').options].map((o) => o.textContent)
    expect(options).toContain('settings.dateFormats.short, 6 janv. 2026')
    expect(options).toContain('settings.dateFormats.long, 6 janvier 2026')
  })
})
