/**
 * A deactivated template is listed only on the profile row that already binds it.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
  initReactI18next: { type: '3rdParty', init: () => {} },
}))
vi.mock('../../../components', () => ({
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Input: (props) => <input {...props} />,
  Select: ({ options }) => <ul data-testid="select">{options.map(o => <li key={o.value}>{o.label}</li>)}</ul>,
}))

import ProfilesEditor from '../ProfilesEditor'

const templates = [
  { id: 3, name: 'Retired', is_active: false },
  { id: 5, name: 'Strict TLS', is_active: true },
]

describe('ProfilesEditor with a deactivated template', () => {
  it('lists it on the row that binds it only', () => {
    const value = {
      bound: { validity_days: 30, digest: 'sha256', template_id: 3 },
      other: { validity_days: 90, digest: 'sha256' },
    }
    render(<ProfilesEditor value={value} onChange={() => {}} templates={templates} />)
    // Each row renders a digest select then a template select
    const templateSelects = screen.getAllByTestId('select').filter(s => s.textContent.includes('acme.noTemplate'))
    expect(templateSelects).toHaveLength(2)
    expect(templateSelects[0].textContent).toContain('Retired')
    expect(templateSelects[1].textContent).not.toContain('Retired')
    expect(templateSelects[1].textContent).toContain('Strict TLS')
  })
})
