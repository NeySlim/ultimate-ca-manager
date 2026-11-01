/**
 * A deactivated template is listed only for the profile name the server has it bound to.
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
    render(<ProfilesEditor value={value} saved={value} onChange={() => {}} templates={templates} />)
    const [bound, other] = templateSelects()
    expect(bound.textContent).toContain('Retired')
    expect(other.textContent).not.toContain('Retired')
    expect(other.textContent).toContain('Strict TLS')
  })

  it('drops it once the saved binding moved on, or under a new name', () => {
    const value = {
      bound: { validity_days: 30, digest: 'sha256', template_id: 3 },
      renamed: { validity_days: 30, digest: 'sha256', template_id: 3 },
    }
    const saved = {
      bound: { validity_days: 30, digest: 'sha256', template_id: 5 },
      before: { validity_days: 30, digest: 'sha256', template_id: 3 },
    }
    render(<ProfilesEditor value={value} saved={saved} onChange={() => {}} templates={templates} />)
    for (const select of templateSelects()) expect(select.textContent).not.toContain('Retired')
  })
})

// Each row renders a digest select then a template select
const templateSelects = () => screen.getAllByTestId('select').filter(s => s.textContent.includes('acme.noTemplate'))
