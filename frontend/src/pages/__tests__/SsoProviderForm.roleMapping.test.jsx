/**
 * SsoProviderForm: role_mapping keeps strings, accepts objects, lists custom roles.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key) => key,
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

vi.mock('../../contexts', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn() }),
  useMobile: () => ({ isMobile: false, isTablet: false, sidebarOpen: true, setSidebarOpen: vi.fn() }),
}))

const listRoles = vi.fn(() => Promise.resolve({ data: [{ id: 1, name: 'Cert Ops' }] }))
vi.mock('../../services', () => ({
  ssoService: {
    getSamlCertificates: vi.fn(() => Promise.resolve({ data: [] })),
    getSamlSpInfo: vi.fn(() => Promise.resolve({ data: {} })),
  },
  rolesService: { listRoles: (...a) => listRoles(...a) },
}))

import SsoProviderForm from '../settings/SsoProviderForm'

const PROVIDER = {
  id: 3, name: 'dir', provider_type: 'ldap', ldap_server: 'ldap.example.test', ldap_base_dn: 'dc=x',
  role_mapping: { staff: 'viewer', ops: { role: null, custom_role: 'Cert Ops' }, blank: '' },
}

const submit = async (onSave) => {
  fireEvent.submit(document.querySelector('form'))
  await waitFor(() => expect(onSave).toHaveBeenCalled())
  return onSave.mock.calls[0][0]
}

describe('SsoProviderForm role mapping', () => {
  it('saves string and object entries unchanged and drops empty ones', async () => {
    const onSave = vi.fn()
    render(<SsoProviderForm provider={PROVIDER} onSave={onSave} onCancel={vi.fn()} />)
    await waitFor(() => expect(listRoles).toHaveBeenCalled())
    const payload = await submit(onSave)
    expect(payload.role_mapping).toEqual({ staff: 'viewer', ops: { role: null, custom_role: 'Cert Ops' } })
  })

  it('renders one base-role and one custom-role selector per row', () => {
    render(<SsoProviderForm provider={PROVIDER} onSave={vi.fn()} onCancel={vi.fn()} />)
    expect(screen.getAllByPlaceholderText('e.g., pki-admins')).toHaveLength(3)
    expect(screen.getAllByText('sso.customRole').length).toBeGreaterThan(0)
  })
})
