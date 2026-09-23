/**
 * AdConnectorForm: the switch is what asks for the credential.
 *
 * update_config requires a bind DN and a bind password only while the
 * connector is enabled, so that a connector saved before the rule existed
 * can still be switched off. The form has to ask the same question, or the
 * rule holds on the API path only and the field is demanded for a connector
 * that binds nothing.
 */
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

vi.mock('../../../contexts', () => ({
  useNotification: () => ({
    showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(),
  }),
}))

vi.mock('../../../services', () => ({
  adConnectorService: { test: vi.fn() },
}))

// The real Input wraps a plain input; what matters here is that `required`
// reaches the DOM node, which is what the browser enforces on submit.
vi.mock('../../../components', () => ({
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Input: ({ label, helperText: _helperText, hasExistingValue: _hasExistingValue, ...props }) =>
    <input aria-label={label} {...props} />,
  Textarea: ({ label, ...props }) => <textarea aria-label={label} {...props} />,
}))

import AdConnectorForm from '../AdConnectorForm'

const renderForm = (config) => render(
  <AdConnectorForm config={config} onSave={vi.fn()} onCancel={vi.fn()} />
)

const bindDn = () => screen.getByLabelText('adConnector.bindDn')
const bindPassword = () => screen.getByLabelText('adConnector.bindPassword')
const enabledSwitch = () => screen.getByLabelText('common.enabled')

const SAVED = {
  id: 1, servers: ['dc1.corp.local'], port: 389, base_dn: 'DC=corp,DC=local',
  bind_dn: 'CN=svc-ucm,DC=corp,DC=local', enabled: false,
}

describe('AdConnectorForm: the credential follows the enabled switch', () => {
  it('asks for neither half while the connector is off', () => {
    renderForm({ ...SAVED, bind_password: null })

    expect(bindDn().required).toBe(false)
    expect(bindPassword().required).toBe(false)
  })

  it('asks for both once the switch is turned on', () => {
    renderForm({ ...SAVED, bind_password: null })

    fireEvent.click(enabledSwitch())

    expect(bindDn().required).toBe(true)
    expect(bindPassword().required).toBe(true)
  })

  it('does not ask again for a password it already has', () => {
    // A blank field means "unchanged": handleSubmit drops it from the
    // payload, so demanding it would ask for a credential the save does
    // not need.
    renderForm({ ...SAVED, bind_password: '***' })

    fireEvent.click(enabledSwitch())

    expect(bindDn().required).toBe(true)
    expect(bindPassword().required).toBe(false)
  })

  it('stops asking when the switch goes back off', () => {
    renderForm({ ...SAVED, bind_password: null, enabled: true })

    expect(bindDn().required).toBe(true)
    fireEvent.click(enabledSwitch())

    expect(bindDn().required).toBe(false)
    expect(bindPassword().required).toBe(false)
  })
})
