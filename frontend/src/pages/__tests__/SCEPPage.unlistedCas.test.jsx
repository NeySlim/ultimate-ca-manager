/**
 * The default CA picker of the SCEP page lists the CAs able to sign, keeps the
 * saved one visible and counts the others (#426).
 */
import { describe, it, expect, vi, beforeAll } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import './pageRenderingSetup.jsx'
import { scepService } from '../../services/scep.service'
import { casService } from '../../services/cas.service'

// The shared setup's `t` drops the options; this one exposes the count.
vi.doMock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (opts?.count !== undefined ? `${key}:${opts.count}` : key),
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

vi.doMock('../../hooks', async (orig) => ({
  ...(await orig()),
  usePermission: () => ({ canWrite: () => true, canDelete: () => true, hasPermission: () => true, canRead: () => true }),
}))

// A native select exposes the options and the helper text that the real one hides in a portal.
vi.doMock('../../components', async (orig) => ({
  ...(await orig()),
  Select: ({ label, options = [], value, onChange, helperText }) => (
    <div data-testid={`field-${label}`}>
      <select aria-label={label} value={value ?? ''} onChange={(e) => onChange?.(e.target.value)}>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
      {helperText && <p>{helperText}</p>}
    </div>
  ),
}))

const CAS = [
  { id: 1, name: 'Signing CA', has_private_key: true },
  { id: 2, name: 'Keyless root', certificate_only: true, has_private_key: false },
  { id: 3, name: 'Offline CA', has_private_key: true, offline: true },
  { id: 4, name: 'HSM CA', uses_hsm: true },
]

let SCEPPage
beforeAll(async () => { SCEPPage = (await import('../SCEPPage')).default })

async function openPicker(savedCaId) {
  Object.assign(scepService, {
    getConfig: vi.fn().mockResolvedValue({ data: { enabled: true, ca_id: savedCaId, challenge_validity_range: [1, 720] } }),
    getRequests: vi.fn().mockResolvedValue({ data: [] }),
    getStats: vi.fn().mockResolvedValue({ data: {} }),
    getProfiles: vi.fn().mockResolvedValue({ data: [] }),
    getChallenge: vi.fn().mockResolvedValue({ data: {} }),
  })
  casService.getAll.mockResolvedValue({ data: CAS })
  render(<MemoryRouter initialEntries={['/scep']}><SCEPPage /></MemoryRouter>)
  fireEvent.click((await screen.findAllByText('common.config'))[0])
  return screen.findByTestId('field-common.issuingCA')
}

const optionValues = (box) => within(box).getAllByRole('option').map((o) => o.textContent)

describe('SCEPPage default CA picker (#426)', () => {
  it('offers only the CA that can sign and counts the others', async () => {
    const box = await openPicker(undefined)
    expect(optionValues(box)).toEqual(['common.none', 'Signing CA'])
    expect(await within(box).findByText('cas.notListedForSigning:3')).toBeInTheDocument()
  })

  it('keeps the saved CA without a key listed and counts one less', async () => {
    const box = await openPicker(2)
    expect(optionValues(box)).toEqual(['common.none', 'Signing CA', 'Keyless root'])
    expect(await within(box).findByText('cas.notListedForSigning:2')).toBeInTheDocument()
  })

  it('can clear the default CA, so the CA can then be deleted', async () => {
    const box = await openPicker(1)
    scepService.updateConfig = vi.fn().mockResolvedValue({ data: {} })
    fireEvent.change(within(box).getByRole('combobox'), { target: { value: '__none__' } })
    fireEvent.click(screen.getByText('common.saveConfiguration'))
    await vi.waitFor(() => expect(scepService.updateConfig).toHaveBeenCalled())
    expect(scepService.updateConfig.mock.calls[0][0].ca_id).toBeNull()
  })
})
