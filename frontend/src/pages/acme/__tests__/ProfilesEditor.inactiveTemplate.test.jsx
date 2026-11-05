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
  const spec = (template_id) => ({ validity_days: 30, digest: 'sha256', ...(template_id ? { template_id } : {}) })
  const render1 = (value, saved) => {
    render(<ProfilesEditor value={value} saved={saved} onChange={() => {}} templates={templates} />)
    return templateSelects()
  }

  it('lists it, marked, on the profile it is bound to only', () => {
    const value = { bound: spec(3), other: spec() }
    const [bound, other] = render1(value, value)
    expect(bound.textContent).toContain('Retired (common.inactive)')
    expect(other.textContent).not.toContain('Retired')
    expect(other.textContent).toContain('Strict TLS')
  })

  it('keeps it offered to go back to the saved binding', () => {
    const [bound] = render1({ bound: spec(5) }, { bound: spec(3) })
    expect(bound.textContent).toContain('Retired')
  })

  it('drops it once the saved binding moved on', () => {
    const [bound] = render1({ bound: spec(5) }, { bound: spec(5) })
    expect(bound.textContent).not.toContain('Retired')
  })

  it('keeps it visible on a renamed row that still carries it', () => {
    const [renamed] = render1({ renamed: spec(3) }, { before: spec(3) })
    expect(renamed.textContent).toContain('Retired (common.inactive)')
  })
})

// Each row renders a digest select then a template select
const templateSelects = () => screen.getAllByTestId('select').filter(s => s.textContent.includes('acme.noTemplate'))
