/**
 * The CA picker of a SCEP profile lists the CAs able to sign, keeps the
 * profile's own CA visible and counts the others (#426).
 */
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'

const mocks = vi.hoisted(() => ({
  getIntuneApps: vi.fn().mockResolvedValue({ data: [] }),
  t: (key, vars) => (vars?.count !== undefined ? `${key}:${vars.count}` : key),
}))

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: mocks.t }) }))
vi.mock('../../../contexts', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showConfirm: vi.fn() }),
}))
vi.mock('../../../hooks/useClipboard', () => ({ useClipboard: () => ({ copy: vi.fn() }) }))
vi.mock('../../../services', () => ({ scepService: mocks }))
vi.mock('../../../components', () => ({
  Button: ({ children, loading: _loading, ...props }) => <button {...props}>{children}</button>,
  Input: ({ label, helperText: _h, noAutofill: _n, ...props }) => <label>{label}<input {...props} /></label>,
  Select: ({ label, value, onChange, options = [], placeholder, helperText }) => (
    <div data-testid={`field-${label}`}>
      <label>{label}
        <select value={value} onChange={(e) => onChange(e.target.value)}>
          <option value="">{placeholder}</option>
          {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </label>
      {helperText && <p>{helperText}</p>}
    </div>
  ),
  Card: ({ children }) => <section>{children}</section>,
  Badge: ({ children }) => <span>{children}</span>,
  Modal: ({ open, children }) => open ? <div role="dialog">{children}</div> : null,
  EmptyState: ({ title }) => <p>{title}</p>,
  HelpCard: ({ children }) => <aside>{children}</aside>,
}))
vi.mock('../../../components/ui/ToggleSwitch', () => ({
  ToggleSwitch: ({ label, checked, onChange }) => (
    <label>{label}<input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} /></label>
  ),
}))

import ScepProfilesTab from '../ScepProfilesTab'

const CAS = [
  { id: 1, refid: 'ca-1', descr: 'Signing CA', has_private_key: true },
  { id: 2, refid: 'ca-2', descr: 'Keyless root', certificate_only: true, has_private_key: false },
  { id: 3, refid: 'ca-3', descr: 'Offline CA', has_private_key: true, offline: true },
  { id: 4, refid: 'ca-4', descr: 'HSM CA', uses_hsm: true },
]
const PROFILE = (ca_refid) => ({ id: 9, name: 'Devices', url_slug: 'devices', ca_refid, enabled: true, auto_approve: false })

const optionLabels = () => within(screen.getByTestId('field-common.certificateAuthority'))
  .getAllByRole('option').filter((o) => o.value !== '').map((o) => o.textContent)

describe('ScepProfilesTab CA picker (#426)', () => {
  it('offers only the CA that can sign and counts the others on a new profile', async () => {
    render(<ScepProfilesTab profiles={[]} cas={CAS} templates={[]} canWrite onChanged={vi.fn()} />)
    fireEvent.click(screen.getByText('scep.newProfile'))
    await screen.findByRole('dialog')
    expect(optionLabels()).toEqual(['Signing CA'])
    expect(screen.getByTestId('field-common.certificateAuthority')).toHaveTextContent('cas.notListedForScep:3')
  })

  it('keeps the profile CA listed when it holds no key and counts one less', async () => {
    render(<ScepProfilesTab profiles={[PROFILE('ca-2')]} cas={CAS} templates={[]} canWrite onChanged={vi.fn()} />)
    fireEvent.click(screen.getByLabelText('common.edit'))
    await screen.findByRole('dialog')
    expect(optionLabels()).toEqual(['Signing CA', 'Keyless root'])
    expect(screen.getByTestId('field-common.certificateAuthority')).toHaveTextContent('cas.notListedForScep:2')
  })
})
