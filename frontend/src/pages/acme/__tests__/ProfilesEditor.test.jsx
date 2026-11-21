/**
 * ACME certificate profiles: template binding (issue #327 follow-up).
 *
 * A profile row carries an optional certificate template; the editor must
 * show the bound template of a stored profile and emit `template_id` as a
 * number (null when unbound) so the settings API can validate it.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import ProfilesEditor from '../ProfilesEditor'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
  initReactI18next: { type: '3rdParty', init: () => {} },
  Trans: ({ children }) => children,
}))

const templates = [
  { id: 3, name: 'mTLS client' },
  { id: 5, name: 'Strict TLS' },
]

const stored = {
  mtls: { description: 'client certs', validity_days: 30, digest: 'sha256', template_id: 3 },
  plain: { description: 'defaults', validity_days: 90, digest: 'sha256' },
}

describe('ProfilesEditor template binding', () => {
  it('shows the bound template of a stored profile and the template column header', () => {
    render(<ProfilesEditor value={stored} onChange={() => {}} templates={templates} />)
    expect(screen.getAllByRole('combobox', { name: /acme\.profileTemplate/ })[0]).toHaveValue('3')
    expect(screen.getAllByText('mTLS client').length).toBeGreaterThan(0)
    // the unbound row shows the "no template" choice
    expect(screen.getAllByText('acme.noTemplate').length).toBeGreaterThan(0)
  })

  it('emits template_id as a number, null when unbound', () => {
    const onChange = vi.fn()
    render(<ProfilesEditor value={stored} onChange={onChange} templates={templates} />)
    fireEvent.click(screen.getByRole('button', { name: /acme\.addProfile/ }))
    const emitted = onChange.mock.calls.at(-1)[0]
    expect(emitted.mtls.template_id).toBe(3)
    expect(emitted.plain.template_id).toBeNull()
  })

  it('keeps working with no templates available', () => {
    render(<ProfilesEditor value={stored} onChange={() => {}} />)
    expect(screen.getAllByText('acme.noTemplate').length).toBeGreaterThan(0)
  })
})
