/**
 * CreateCAModal RSA signature scheme: PKCS#1 v1.5 by default, RSA-PSS on
 * request for an RSA key, never offered for EC or an HSM that cannot sign it.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

const mocks = vi.hoisted(() => ({
  create: vi.fn(),
  getProviders: vi.fn(),
  showSuccess: vi.fn(),
  showError: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

vi.mock('../../../services', () => ({
  casService: { create: mocks.create },
  hsmService: { getProviders: mocks.getProviders, getSigningKeys: vi.fn() },
}))

vi.mock('../../../contexts', () => ({
  useNotification: () => ({ showSuccess: mocks.showSuccess, showError: mocks.showError }),
}))

vi.mock('../../../hooks', () => ({
  useWebSocket: () => ({ muteToasts: vi.fn() }),
}))

vi.mock('../../../lib/utils', () => ({
  extractData: (r) => r?.data ?? r,
  cn: (...a) => a.filter(Boolean).join(' '),
  downloadBlob: vi.fn(),
}))

vi.mock('../../../components', () => ({
  Modal: ({ open, children }) => (open ? <div>{children}</div> : null),
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Input: ({ label, helperText: _h, ...props }) => <input aria-label={label || props.name} {...props} />,
  Select: ({ label, options = [], value, onChange }) => (
    <select
      aria-label={label}
      value={value ?? ''}
      onChange={(e) => onChange?.(e.target.value)}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  ),
}))

import { CreateCAModal } from '../CreateCAModal'

async function openRoot(providers = []) {
  mocks.getProviders.mockResolvedValue({ data: providers })
  mocks.create.mockResolvedValue({ data: { id: 1 } })
  render(<CreateCAModal open onClose={vi.fn()} cas={[]} onSuccess={vi.fn()} />)
  fireEvent.change(screen.getByLabelText('common.commonName (CN)'), {
    target: { value: 'Short Root' },
  })
}

async function submittedPayload() {
  fireEvent.click(screen.getByText('common.createCA'))
  await waitFor(() => expect(mocks.create).toHaveBeenCalled())
  return mocks.create.mock.calls[0][0]
}

const schemeOptions = () =>
  [...screen.getByLabelText('cas.signatureScheme').querySelectorAll('option')].map((o) => o.value)

describe('CreateCAModal signature scheme', () => {
  beforeEach(() => vi.clearAllMocks())

  it('sends PKCS#1 v1.5 by default', async () => {
    await openRoot()
    expect((await submittedPayload()).signatureScheme).toBe('pkcs1v15')
  })

  it('sends RSA-PSS when chosen', async () => {
    await openRoot()
    fireEvent.change(screen.getByLabelText('cas.signatureScheme'), { target: { value: 'pss' } })
    expect((await submittedPayload()).signatureScheme).toBe('pss')
  })

  it('offers nothing for an EC key', async () => {
    await openRoot()
    fireEvent.change(screen.getByLabelText('cas.signatureScheme'), { target: { value: 'pss' } })
    fireEvent.change(screen.getByLabelText('common.keyAlgorithm'), { target: { value: 'ECDSA' } })
    expect(screen.queryByLabelText('cas.signatureScheme')).toBeNull()
    expect((await submittedPayload()).signatureScheme).toBeUndefined()
  })

  it('falls back to PKCS#1 v1.5 once PSS stops being possible', async () => {
    await openRoot()
    fireEvent.change(screen.getByLabelText('cas.signatureScheme'), { target: { value: 'pss' } })
    fireEvent.change(screen.getByLabelText('common.keyAlgorithm'), { target: { value: 'ECDSA' } })
    fireEvent.change(screen.getByLabelText('common.keyAlgorithm'), { target: { value: 'RSA' } })
    expect(screen.getByLabelText('cas.signatureScheme').value).toBe('pkcs1v15')
  })

  it('offers RSA-PSS on a PKCS#11 provider, not on Azure', async () => {
    await openRoot([
      { id: 1, name: 'vault', provider_type: 'azure-keyvault', enabled: true },
      { id: 2, name: 'token', provider_type: 'pkcs11', enabled: true },
    ])
    fireEvent.click(screen.getByLabelText('cas.create.keyStorageHsm'))
    await waitFor(() => expect(screen.getByLabelText('cas.create.hsmProvider')).toBeTruthy())
    fireEvent.change(screen.getByLabelText('cas.create.hsmProvider'), { target: { value: '1' } })
    expect(schemeOptions()).toEqual(['pkcs1v15'])
    fireEvent.change(screen.getByLabelText('cas.create.hsmProvider'), { target: { value: '2' } })
    expect(schemeOptions()).toEqual(['pkcs1v15', 'pss'])
  })
})
