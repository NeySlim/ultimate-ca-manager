/**
 * Both signing-CA pickers of the TSA page (settings and signer generation)
 * list the CAs able to sign, keep the chosen one visible and count the others (#426).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (opts && typeof opts.count === 'number' ? `${key}:${opts.count}` : key),
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

vi.mock('../../contexts', () => ({
  useAuth: () => ({ user: { id: 1, username: 'op', role: 'operator' } }),
  useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn() }),
  useMobile: () => ({ isMobile: false, isTablet: false, sidebarOpen: true, setSidebarOpen: vi.fn() }),
  useTheme: () => ({ theme: 'dark', setTheme: vi.fn(), resolvedTheme: 'dark', themes: ['light', 'dark'] }),
  useInspector: () => ({
    openEntity: vi.fn(), closeWindow: vi.fn(), windows: [],
    prefs: { sameWindow: true, closeOnNav: true }, updatePrefs: vi.fn(),
  }),
  AuthProvider: ({ children }) => children,
  ThemeProvider: ({ children }) => children,
  NotificationProvider: ({ children }) => children,
  MobileProvider: ({ children }) => children,
  InspectorProvider: ({ children }) => children,
}))

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ permissions: ['read:settings', 'write:settings', 'write:certificates', 'read:cas'] }),
}))

vi.mock('../../hooks/useWebSocket', () => ({
  useWebSocket: () => ({ subscribe: vi.fn(() => vi.fn()), isConnected: false }),
  WebSocketProvider: ({ children }) => children,
  EventType: {},
  ConnectionState: { DISCONNECTED: 'disconnected' },
}))

vi.mock('../../services/cas.service', () => ({
  casService: {
    getAll: vi.fn().mockResolvedValue({ data: [
      { id: 1, refid: 'ca-sign', name: 'Signing CA', has_private_key: true },
      { id: 2, refid: 'ca-keyless', name: 'Keyless root', certificate_only: true, has_private_key: false },
      { id: 3, refid: 'ca-offline', name: 'Offline CA', has_private_key: true, offline: true },
      { id: 4, refid: 'ca-root', name: 'Hidden root', has_private_key: true, issuance_hidden: true },
    ] }),
  },
}))

vi.mock('../../services/tsa.service', () => ({
  tsaService: {
    getConfig: vi.fn(),
    updateConfig: vi.fn().mockResolvedValue({ data: {} }),
    getStats: vi.fn().mockResolvedValue({ data: { total: 0 } }),
    getSignerCandidates: vi.fn().mockResolvedValue({ data: [] }),
  },
}))

import TSAPage from '../TSAPage'
import { tsaService } from '../../services/tsa.service'

async function openSettings(ca_refid) {
  tsaService.getConfig.mockResolvedValue({
    data: { enabled: true, ca_refid, policy_oid: '1.2.3.4.1', signer_cert_refid: '', signer: { configured: false } },
  })
  render(<MemoryRouter initialEntries={['/tsa-config?tab=config']}><TSAPage /></MemoryRouter>)
  await screen.findByText('tsa.signingCertDesc')
  // The settings picker is the configuration form's own select, in its .field with the hint
  return (await screen.findByRole('combobox', { name: 'tsa.signingCA' })).closest('.field')
}

const labels = (field) => within(field).getAllByRole('option').filter((o) => o.value !== '' && o.value !== '__hidden_cas__').map((o) => o.textContent)
const generationField = () => within(screen.getByRole('dialog')).getByLabelText('tsa.signingCA').closest('.field')
// Picks a CA the way a saved value would, even one the select does not list
function chooseUnlisted(field, value) {
  const select = within(field).getByRole('combobox')
  const stray = document.createElement('option')
  stray.value = value
  select.appendChild(stray)
  fireEvent.change(select, { target: { value } })
  stray.remove()
}

describe('TSAPage signing CA pickers (#426)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    tsaService.getStats.mockResolvedValue({ data: { total: 0 } })
    tsaService.getSignerCandidates.mockResolvedValue({ data: [] })
  })

  it('settings picker offers only the CAs that can sign, a CA hidden from issuance (#430) included', async () => {
    const field = await openSettings('ca-sign')
    expect(labels(field)).toEqual(['Signing CA', 'Hidden root'])
    expect(field).toHaveTextContent('cas.notListedForSigning:2')
  })

  it('settings picker keeps the saved CA without a key listed and counts one less', async () => {
    const field = await openSettings('ca-keyless')
    expect(labels(field)).toEqual(['Signing CA', 'Hidden root', 'Keyless root'])
    expect(field).toHaveTextContent('cas.notListedForSigning:1')
  })

  it('generation picker keeps a CA hidden from issuance behind its link (#430)', async () => {
    await openSettings('ca-sign')
    fireEvent.click(await screen.findByText('tsa.signerGenerate'))
    await screen.findByText('tsa.signerGenerateModalDesc')
    const field = generationField()
    expect(labels(field)).toEqual(['Signing CA'])
    // The link of the issue form: the select's last option shows the hidden CAs
    fireEvent.change(within(field).getByRole('combobox'), { target: { value: '__hidden_cas__' } })
    expect(within(field).getByRole('option', { name: 'cas.hideHiddenCas' })).toBeInTheDocument()
    expect(labels(field)).toEqual(['Signing CA', 'Hidden root'])
  })

  it('generation picker follows its own selection, not the saved setting', async () => {
    await openSettings('ca-sign')
    fireEvent.click(await screen.findByText('tsa.signerGenerate'))
    await screen.findByText('tsa.signerGenerateModalDesc')
    const field = generationField()
    expect(labels(field)).toEqual(['Signing CA'])
    expect(field).toHaveTextContent('cas.notListedForSigning:2')
    chooseUnlisted(field, 'ca-keyless')
    expect(labels(field)).toEqual(['Signing CA', 'Keyless root'])
    expect(field).toHaveTextContent('cas.notListedForSigning:1')
  })
})
