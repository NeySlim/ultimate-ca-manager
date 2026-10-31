/** ACME account keys come from the registry: the ACME client keys a JWS algorithm can sign with. */
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { ACME_CLIENT_LABELS, GROUP_NIST, GROUP_RSA, findAlgorithm } from '../../../lib/keyAlgorithms'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

vi.mock('../../../contexts', () => ({
  useNotification: () => ({ showWarning: vi.fn() }),
}))

vi.mock('../../../components', () => ({
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Input: ({ label, helperText, ...props }) => <input aria-label={label} {...props} />,
  Select: ({ label, value, onChange, options }) => (
    <select aria-label={label} value={value ?? ''} onChange={(e) => onChange(e.target.value)}>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  ),
}))

import CreateAccountForm from '../CreateAccountForm'

// RFC 7518 signs with RSA or a NIST curve: Brainpool has no JWS algorithm
const ACCOUNT_LABELS = ACME_CLIENT_LABELS.filter(l => [GROUP_RSA, GROUP_NIST].includes(findAlgorithm(l).group))

function renderForm() {
  const onSubmit = vi.fn()
  render(<CreateAccountForm onSubmit={onSubmit} onCancel={vi.fn()} />)
  fireEvent.change(screen.getByLabelText('common.emailAddress'), { target: { value: 'a@example.com' } })
  fireEvent.click(screen.getByRole('checkbox'))
  return onSubmit
}

const submit = () => fireEvent.submit(screen.getByLabelText('common.keyType').closest('form'))

describe('CreateAccountForm key types', () => {
  it('offers the ACME client keys a JWS algorithm can sign with, named by the registry', () => {
    renderForm()
    const options = Array.from(screen.getByLabelText('common.keyType').options)
    expect(options.map(o => o.value)).toEqual(ACCOUNT_LABELS)
    expect(options.map(o => o.textContent)).toEqual(ACCOUNT_LABELS.map(l => findAlgorithm(l).display))
  })

  it('starts on the first of them', () => {
    const onSubmit = renderForm()
    submit()
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ key_type: ACCOUNT_LABELS[0] }))
  })

  it.each(ACCOUNT_LABELS)('sends %s as picked', (label) => {
    const onSubmit = renderForm()
    fireEvent.change(screen.getByLabelText('common.keyType'), { target: { value: label } })
    submit()
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ key_type: label }))
  })
})
