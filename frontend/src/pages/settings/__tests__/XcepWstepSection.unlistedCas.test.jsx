/**
 * The CA pickers of XCEP and WSTEP list the CAs able to sign, keep the CA
 * saved for either protocol visible and count the others (#426).
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// Stable references: the section reloads whenever `t` or the notifier changes identity.
const mocks = vi.hoisted(() => ({
  t: (key, opts) => (opts?.count !== undefined ? `${key}:${opts.count}` : key),
  notify: { showSuccess: () => {}, showError: () => {}, showConfirm: () => {} },
  getXcep: vi.fn(),
  getWstep: vi.fn(),
  CAS: [
    { id: 1, descr: 'Signing CA', has_private_key: true },
    { id: 2, descr: 'Keyless root', certificate_only: true, has_private_key: false },
    { id: 3, descr: 'Offline CA', has_private_key: true, offline: true },
  ],
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: mocks.t,
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../../../contexts', () => ({
  useNotification: () => mocks.notify,
  useMobile: () => ({ isMobile: false, isTablet: false, sidebarOpen: true, setSidebarOpen: vi.fn() }),
}))

vi.mock('../../../services', () => ({
  xcepWstepService: { getXcep: mocks.getXcep, getWstep: mocks.getWstep },
  casService: { getAll: vi.fn().mockResolvedValue({ data: mocks.CAS }) },
  adConnectorService: { get: vi.fn().mockResolvedValue({ data: null }) },
  kerberosService: { get: vi.fn().mockResolvedValue({ data: null }) },
  templatesService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
}))

// A native select exposes the options and the helper text that the real one hides in a portal.
vi.mock('../../../components', async (orig) => ({
  ...(await orig()),
  Select: ({ label, options = [], value, helperText }) => (
    <div data-testid={`field-${label}`}>
      <select aria-label={label} value={value ?? ''} onChange={() => {}}>
        <option value="">-</option>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
      {helperText && <p>{helperText}</p>}
    </div>
  ),
}))

import XcepWstepSection from '../XcepWstepSection'

async function renderSection(xcep, wstep) {
  mocks.getXcep.mockResolvedValue({ data: { enabled: true, ca_id: null, username: '', password_set: false, ...xcep } })
  mocks.getWstep.mockResolvedValue({ data: { enabled: true, ca_id: null, username: '', password_set: false, validity_days: 365, ...wstep } })
  render(<MemoryRouter><XcepWstepSection /></MemoryRouter>)
  await screen.findAllByTestId('field-xcepWstep.ca')
  return screen.getAllByTestId('field-xcepWstep.ca')
}

const labels = (field) => within(field).getAllByRole('option').filter((o) => o.value !== '').map((o) => o.textContent)

describe('XcepWstepSection CA pickers (#426)', () => {
  it('offers only the CA that can sign and counts the others', async () => {
    const fields = await renderSection({}, {})
    expect(fields).toHaveLength(2)
    for (const field of fields) {
      expect(labels(field)).toEqual(['Signing CA'])
      expect(field).toHaveTextContent('cas.notListedForSigning:2')
    }
  })

  it('keeps the XCEP CA without a key listed in both pickers and counts one less', async () => {
    const fields = await renderSection({ ca_id: 2 }, {})
    for (const field of fields) {
      expect(labels(field)).toEqual(['Signing CA', 'Keyless root'])
      expect(field).toHaveTextContent('cas.notListedForSigning:1')
    }
  })

  it('keeps the WSTEP CA without a key listed in both pickers and counts one less', async () => {
    const fields = await renderSection({}, { ca_id: 2 })
    for (const field of fields) {
      expect(labels(field)).toEqual(['Signing CA', 'Keyless root'])
      expect(field).toHaveTextContent('cas.notListedForSigning:1')
    }
  })
})
