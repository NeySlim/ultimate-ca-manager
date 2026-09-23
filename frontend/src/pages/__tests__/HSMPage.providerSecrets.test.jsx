/**
 * HSM provider form: saving without retyping a secret keeps the stored one.
 * The API masks each secret as '***' and keeps the stored value on that sentinel;
 * an empty string would overwrite it.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import './pageRenderingSetup.jsx'

import { ProviderModal } from '../HSMPage'

const CASES = [
  ['pkcs11', { pkcs11_library_path: '/usr/lib/softhsm/libsofthsm2.so', pkcs11_token_label: 'UCM-Default', pkcs11_pin: '***' }, 'user_pin'],
  ['aws-cloudhsm', { aws_cluster_id: 'c-1', aws_crypto_user: 'cu', aws_crypto_password: '***' }, 'hsm_password'],
  ['azure-keyvault', { azure_vault_url: 'https://v.vault.azure.net', azure_client_secret: '***' }, 'client_secret'],
  ['openbao', { openbao_url: 'https://bao.example', openbao_token: '***' }, 'token'],
]

describe('HSM provider form, stored secrets', () => {
  it.each(CASES)('%s: a save without retyping sends the kept sentinel', async (type, fields, key) => {
    const onSave = vi.fn()
    render(<ProviderModal provider={{ id: 1, name: 'P', provider_type: type, ...fields }}
                          hsmStatus={null} onSave={onSave} onClose={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: 'common.save' }))
    await waitFor(() => expect(onSave).toHaveBeenCalled())
    expect(onSave.mock.calls[0][0].config[key]).toBe('***')
  })

})
