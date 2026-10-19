/**
 * AdConnectorForm: the saved bind password stays with the saved DCs, port and
 * TLS trust. Moving any of them asks for the password before saving.
 */
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

const showError = vi.fn()
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }) }))
vi.mock('../../../contexts', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError, showWarning: vi.fn() }),
}))
vi.mock('../../../services', () => ({ adConnectorService: { test: vi.fn() } }))
vi.mock('../../../components', () => ({
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Input: ({ label, helperText: _h, hasExistingValue: _e, error, ...props }) => (
    <>
      <input aria-label={label} {...props} />
      {error && <p>{error}</p>}
    </>
  ),
  Textarea: ({ label, ...props }) => <textarea aria-label={label} {...props} />,
}))

import AdConnectorForm from '../AdConnectorForm'

const SAVED = {
  id: 1, servers: ['dc1.corp.local', 'dc2.corp.local'], port: 636, use_ssl: true, verify_ssl: true,
  base_dn: 'DC=corp,DC=local', bind_dn: 'CN=svc,DC=corp,DC=local', bind_password: '***', enabled: true,
}

const setup = () => {
  const onSave = vi.fn()
  showError.mockClear()
  const { container } = render(<AdConnectorForm config={SAVED} onSave={onSave} onCancel={vi.fn()} />)
  const submit = () => fireEvent.submit(container.querySelector('form'))
  return { onSave, submit }
}

describe('AdConnectorForm: saved password and target', () => {
  it('refuses to move the port without the password', () => {
    const { onSave, submit } = setup()
    fireEvent.change(screen.getByLabelText('adConnector.port'), { target: { value: '389' } })
    expect(screen.getByText('common.secretRequiredForTarget')).toBeInTheDocument()
    expect(screen.getByLabelText('adConnector.bindPassword').required).toBe(true)
    submit()
    expect(onSave).not.toHaveBeenCalled()
    expect(showError).toHaveBeenCalledWith('common.secretRequiredForTarget')
  })

  it('saves a moved port once the password is typed', () => {
    const { onSave, submit } = setup()
    fireEvent.change(screen.getByLabelText('adConnector.port'), { target: { value: '389' } })
    fireEvent.change(screen.getByLabelText('adConnector.bindPassword'), { target: { value: 'typed' } })
    submit()
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ port: 389, bind_password: 'typed' }))
  })

  it('keeps the saved password for other edits, and for dropping a DC', () => {
    const { onSave, submit } = setup()
    fireEvent.change(screen.getByLabelText('adConnector.baseDn'), { target: { value: 'DC=other' } })
    fireEvent.click(screen.getAllByLabelText('common.remove')[1])
    expect(screen.queryByText('common.secretRequiredForTarget')).not.toBeInTheDocument()
    submit()
    expect(onSave).toHaveBeenCalledWith(expect.not.objectContaining({ bind_password: expect.anything() }))
  })
})
