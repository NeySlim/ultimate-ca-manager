/**
 * AWS CloudHSM form: it sends what the PKCS#11 provider logs in with
 * (module, token label, crypto user and password), and no AWS API credentials.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import './pageRenderingSetup.jsx'

import { ProviderModal } from '../HSMPage'

describe('HSM provider form, AWS CloudHSM', () => {
  it('sends the token label and crypto user, no region or access key', async () => {
    const onSave = vi.fn()
    render(<ProviderModal provider={{ id: 2, name: 'C', provider_type: 'aws-cloudhsm',
                                      aws_cluster_id: 'cluster-1', aws_crypto_user: 'cu',
                                      aws_crypto_password: '***' }}
                          hsmStatus={null} onSave={onSave} onClose={() => {}} />)
    expect(screen.queryByText('hsm.awsConfig.region')).toBeNull()
    expect(screen.queryByText('hsm.awsConfig.accessKey')).toBeNull()
    const field = screen.getByText('hsm.pkcs11Config.tokenLabel').closest('div').querySelector('input')
    fireEvent.change(field, { target: { value: 'hsm1' } })
    fireEvent.click(screen.getByRole('button', { name: 'common.save' }))
    await waitFor(() => expect(onSave).toHaveBeenCalled())
    const { config } = onSave.mock.calls[0][0]
    expect(config).toMatchObject({ token_label: 'hsm1', hsm_user: 'cu', hsm_password: '***',
                                   cluster_id: 'cluster-1' })
    expect(config.module_path).toBeTruthy()
    expect(config).not.toHaveProperty('region')
    expect(config).not.toHaveProperty('access_key')
  })
})
