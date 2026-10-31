import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const getClientSettings = vi.fn()

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

vi.mock('../../../contexts', () => ({
  useNotification: () => ({ showWarning: vi.fn() }),
}))

vi.mock('../../../services', () => ({
  acmeService: { getClientSettings: (...args) => getClientSettings(...args) },
}))

vi.mock('../../../components', () => ({
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Input: ({ label, helperText, ...props }) => <input aria-label={label} {...props} />,
  Select: ({ label, value, onChange, options }) => (
    <select aria-label={label} value={value ?? ''} onChange={(e) => onChange(e.target.value)}>
      <option value="" />
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  ),
}))

import RequestCertificateForm from '../RequestCertificateForm'

const renderForm = (props = {}) => {
  const onSubmit = vi.fn()
  render(
    <RequestCertificateForm
      onSubmit={onSubmit}
      onPreflight={vi.fn()}
      onCancel={vi.fn()}
      dnsProviders={[]}
      defaultEnvironment="staging"
      defaultEmail="admin@example.com"
      {...props}
    />,
  )
  return onSubmit
}

const submit = () => {
  fireEvent.change(screen.getByRole('textbox', { name: '' }), { target: { value: 'example.com' } })
  fireEvent.click(screen.getByText('acme.requestCertificate'))
}

describe('RequestCertificateForm key type', () => {
  beforeEach(() => {
    getClientSettings.mockReset()
  })

  it('starts from the key type configured for the ACME client', async () => {
    getClientSettings.mockResolvedValue({ data: { key_type: 'EC-P384' } })
    const onSubmit = renderForm()

    await waitFor(() => expect(screen.getByLabelText('acme.keyType').value).toBe('EC-P384'))
    submit()
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ key_type: 'EC-P384' }))
  })

  it('leaves the choice to the server when the settings cannot be read', async () => {
    getClientSettings.mockRejectedValue(new Error('offline'))
    const onSubmit = renderForm()

    await waitFor(() => expect(getClientSettings).toHaveBeenCalled())
    submit()
    expect(onSubmit.mock.calls[0][0]).not.toHaveProperty('key_type')
  })

  it('keeps a type the user picked before the settings arrive', async () => {
    let resolve
    getClientSettings.mockReturnValue(new Promise((r) => { resolve = r }))
    const onSubmit = renderForm()

    fireEvent.change(screen.getByLabelText('acme.keyType'), { target: { value: 'RSA-4096' } })
    resolve({ data: { key_type: 'EC-P256' } })
    await waitFor(() => expect(getClientSettings).toHaveBeenCalled())
    await Promise.resolve()
    submit()
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ key_type: 'RSA-4096' }))
  })

  it('uses a default passed by the caller without fetching', () => {
    const onSubmit = renderForm({ defaultKeyType: 'EC-P256' })

    expect(getClientSettings).not.toHaveBeenCalled()
    submit()
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ key_type: 'EC-P256' }))
  })
})

describe('RequestCertificateForm Brainpool', () => {
  beforeEach(() => {
    getClientSettings.mockReset()
    getClientSettings.mockResolvedValue({ data: {} })
  })

  it('offers EC-BP256 and EC-BP384 only, with the compatibility notice once picked', () => {
    renderForm()
    const values = Array.from(screen.getByLabelText('acme.keyType').options).map((o) => o.value).filter(Boolean)
    expect(values).toEqual(['RSA-2048', 'RSA-4096', 'EC-P256', 'EC-P384', 'EC-BP256', 'EC-BP384'])
    expect(screen.queryByRole('note')).toBeNull()
    fireEvent.change(screen.getByLabelText('acme.keyType'), { target: { value: 'EC-BP384' } })
    expect(screen.getByRole('note').textContent).toContain('common.keyGroups.brainpoolWarning')
  })

  it('accepts a configured Brainpool default', () => {
    const onSubmit = renderForm({ defaultKeyType: 'EC-BP256' })
    submit()
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ key_type: 'EC-BP256' }))
  })
})
