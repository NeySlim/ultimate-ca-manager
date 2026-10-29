/**
 * The default CA picker and the label mapping of the EST page list the CAs
 * able to sign, keep the saved ones visible and count the others (#426).
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'

const mocks = vi.hoisted(() => ({ getConfig: vi.fn(), getAll: vi.fn() }))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (opts?.count !== undefined ? `${key}:${opts.count}` : key),
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../../contexts', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn() }),
}))
vi.mock('../../hooks', () => ({
  usePermission: () => ({ hasPermission: () => true, canWrite: () => true }),
  useClipboard: () => ({ copy: vi.fn() }),
}))
vi.mock('../../services', () => ({
  estService: { getConfig: mocks.getConfig, getStats: vi.fn().mockResolvedValue({ data: {} }) },
  casService: { getAll: mocks.getAll },
}))
vi.mock('../settings/MappingEditor', () => ({
  default: ({ value, valueOptions = [] }) => (
    <div data-testid="labels">
      <span data-testid="label-values">{JSON.stringify(value)}</span>
      <ul>{valueOptions.map((o) => <li key={o.value}>{o.label}</li>)}</ul>
    </div>
  ),
}))
// A native select exposes the options and the helper text that the real one hides in a portal.
vi.mock('../../components', async (orig) => ({
  ...(await orig()),
  ResponsiveLayout: ({ children }) => <div>{children}</div>,
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

import ESTPage from '../ESTPage'

const CAS = [
  { id: 1, refid: 'ca-sign', name: 'Signing CA', has_private_key: true },
  { id: 2, refid: 'ca-keyless', name: 'Keyless root', certificate_only: true, has_private_key: false },
  { id: 3, refid: 'ca-offline', name: 'Offline CA', has_private_key: true, offline: true },
]

async function renderPage(config) {
  mocks.getConfig.mockResolvedValue({ data: { enabled: true, ...config } })
  mocks.getAll.mockResolvedValue({ data: CAS })
  render(<ESTPage />)
  return {
    caField: await screen.findByTestId('field-common.issuingCA'),
    labels: await screen.findByTestId('labels'),
  }
}

const caLabels = (field) => within(field).getAllByRole('option').filter((o) => o.value !== '').map((o) => o.textContent)
const labelOptions = (box) => within(box).getAllByRole('listitem').map((o) => o.textContent)

describe('ESTPage CA pickers (#426)', () => {
  it('default CA: offers only the CA that can sign and counts the others', async () => {
    const { caField } = await renderPage({})
    expect(caLabels(caField)).toEqual(['Signing CA'])
    expect(caField).toHaveTextContent('cas.notListedForSigning:2')
  })

  it('default CA: keeps the saved CA without a key listed and counts one less', async () => {
    const { caField } = await renderPage({ ca_id: 2 })
    expect(caLabels(caField)).toEqual(['Signing CA', 'Keyless root'])
    expect(caField).toHaveTextContent('cas.notListedForSigning:1')
  })

  it('labels: offers only the CA that can sign and counts the others', async () => {
    const { labels } = await renderPage({ labels: { web: { ca_refid: 'ca-sign', ca_name: 'Signing CA' } } })
    expect(labelOptions(labels)).toEqual(['Signing CA'])
    expect(labels.parentElement).toHaveTextContent('cas.notListedForSigning:2')
  })

  it('labels: flattens the loaded mapping and keeps a label CA without a key listed', async () => {
    const { labels } = await renderPage({
      labels: { web: { ca_refid: 'ca-sign', ca_name: 'Signing CA' }, lab: { ca_refid: 'ca-keyless', ca_name: 'Keyless root' } },
    })
    expect(JSON.parse(within(labels).getByTestId('label-values').textContent)).toEqual({ web: 'ca-sign', lab: 'ca-keyless' })
    expect(labelOptions(labels)).toEqual(['Signing CA', 'Keyless root'])
    expect(labels.parentElement).toHaveTextContent('cas.notListedForSigning:1')
  })
})
