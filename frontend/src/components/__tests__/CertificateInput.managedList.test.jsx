/**
 * CertificateInput — the "managed certificate" dropdown asks for what it means
 * (DUP-FE-014b).
 *
 * The list was requested with `{ has_key, limit: 500 }`. `/api/v2/certificates`
 * reads page / per_page / status / ca_id / source / search / template_modified /
 * sort_by / sort_order and nothing else, so both were dropped on the floor: the
 * dropdown showed the first 20 certificates by subject, private key or not,
 * with no error and no sign of truncation.
 *
 * The endpoint offers no "has a private key" filter, so the key check belongs
 * on the client, over a page size the endpoint really honours (100 max).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key) => key,
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

// Radix Select renders its items in a portal only once open; a plain <select>
// exposes the same option list to the test.
vi.mock('../Select', () => ({
  SelectComponent: ({ label, options = [], onChange, disabled }) => (
    <select
      aria-label={label}
      disabled={disabled}
      onChange={(e) => onChange && onChange(e.target.value)}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  ),
}))

const getAll = vi.fn()
vi.mock('../../services', () => ({
  apiClient: { post: vi.fn().mockResolvedValue({ data: { objects: [] } }) },
  certificatesService: {
    getAll: (...a) => getAll(...a),
    getById: vi.fn().mockResolvedValue({ data: {} }),
    export: vi.fn(),
  },
}))

import { CertificateInput } from '../CertificateInput'

const cert = (id, hasKey) => ({
  id, descr: `cert-${id}`, common_name: `cert-${id}`, has_private_key: hasKey,
})

async function openManagedMode(props = {}) {
  render(<CertificateInput value={{ cert_pem: '', key_pem: '' }} onChange={vi.fn()} {...props} />)
  fireEvent.click(screen.getByText('certInput.modeManaged'))
  await waitFor(() => expect(getAll).toHaveBeenCalled())
}

const optionLabels = () =>
  Array.from(document.querySelectorAll('option')).map((o) => o.textContent)

describe('DUP-FE-014b — managed certificate dropdown', () => {
  beforeEach(() => {
    getAll.mockReset()
    getAll.mockResolvedValue({ data: [], meta: { total: 0 } })
  })

  it('sends only parameters the endpoint reads', async () => {
    await openManagedMode({ requireKey: true })
    const params = getAll.mock.calls[0][0] || {}
    expect('has_key' in params).toBe(false)
    expect('limit' in params).toBe(false)
    expect(params.per_page).toBe(100)
    expect(params.page).toBe(1)
  })

  it('keeps only the certificates that hold a private key when one is required', async () => {
    getAll.mockResolvedValue({
      data: [cert(1, true), cert(2, false), cert(3, true)],
      meta: { total: 3 },
    })
    await openManagedMode({ requireKey: true })
    await waitFor(() => expect(optionLabels().length).toBe(3)) // placeholder + 2
    const labels = optionLabels().join('|')
    expect(labels).toContain('cert-1')
    expect(labels).toContain('cert-3')
    expect(labels).not.toContain('cert-2')
  })

  it('says so when none of the certificates holds a private key', async () => {
    getAll.mockResolvedValue({ data: [cert(1, false), cert(2, false)], meta: { total: 2 } })
    await openManagedMode({ requireKey: true })
    expect(await screen.findByText('certInput.noCertsWithKey')).toBeTruthy()
  })

  it('names a certificate by its CN with the description alongside (#365)', async () => {
    getAll.mockResolvedValue({
      data: [{ id: 9, common_name: 'host.example.com', descr: 'Renamed', has_private_key: true }],
      meta: { total: 1 },
    })
    await openManagedMode({ requireKey: true })
    await waitFor(() => expect(optionLabels()).toContain('host.example.com · Renamed 🔑'))
  })

  it('lists every certificate when no private key is required', async () => {
    getAll.mockResolvedValue({ data: [cert(1, true), cert(2, false)], meta: { total: 2 } })
    await openManagedMode({ requireKey: false })
    await waitFor(() => expect(optionLabels().length).toBe(3))
    expect(optionLabels().join('|')).toContain('cert-2')
  })

  it('walks the remaining pages when the first one is not the whole list', async () => {
    const page1 = Array.from({ length: 100 }, (_, i) => cert(i + 1, true))
    const page2 = Array.from({ length: 30 }, (_, i) => cert(i + 101, true))
    getAll.mockImplementation(({ page }) =>
      Promise.resolve({ data: page === 1 ? page1 : page2, meta: { total: 130 } }))
    await openManagedMode({ requireKey: true })
    await waitFor(() => expect(optionLabels().length).toBe(131)) // placeholder + 130
    expect(optionLabels().join('|')).toContain('cert-130')
  })
})
