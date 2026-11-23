/**
 * The HSM provider as typed rows: a URL or a path in a chip that copies it whole, an identifier
 * in a chip, a value the provider does not hold muted.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, fireEvent, waitFor } from '@testing-library/react'
import './pageRenderingSetup.jsx'

import { ProviderConfig, ModuleSection } from '../HSMPage'

const row = (term) => {
  const found = [...document.querySelectorAll('dl.kv > div.row')].find((r) => r.querySelector('dt').textContent === term)
  if (!found) throw new Error(`no row ${term}`)
  return found
}
let writeText
beforeEach(() => {
  writeText = vi.fn().mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
  Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true })
})

describe('the configuration of a provider', () => {
  it('shows the vault URL in a chip that copies it whole, a missing tenant muted', async () => {
    const vault = 'https://corp-signing-vault.vault.azure.net/'
    render(<ProviderConfig provider={{ provider_type: 'azure-keyvault', azure_vault_url: vault, azure_client_id: '0f6b3c2e-1d4a-4c5b-9e8f-7a6b5c4d3e2f' }} />)
    const url = row('hsm.azureConfig.vaultUrl')
    expect(url).toHaveClass('long')
    expect(url.querySelector('.code-value.url .val')).toHaveAttribute('title', vault)
    fireEvent.click(url.querySelector('.code-value .cp'))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(vault))
    expect(row('hsm.azureConfig.tenant').querySelector('dd')).toHaveClass('absent')
    expect(row('hsm.azureConfig.client').querySelector('dd.v .code-value')).toHaveTextContent('0f6b3c2e-1d4a-4c5b-9e8f-7a6b5c4d3e2f')
  })

  it('shows the PKCS#11 library path in a chip, and its absence muted', () => {
    const { unmount } = render(<ProviderConfig provider={{ provider_type: 'pkcs11', pkcs11_library_path: '/usr/lib/softhsm/libsofthsm2.so', pkcs11_token_label: 'ucm' }} />)
    expect(row('hsm.pkcs11Config.libraryPath').querySelector('.code-value.url .val')).toHaveAttribute('title', '/usr/lib/softhsm/libsofthsm2.so')
    unmount()
    render(<ProviderConfig provider={{ provider_type: 'pkcs11' }} />)
    expect(row('hsm.pkcs11Config.libraryPath').querySelector('dd')).toHaveClass('absent')
    expect(row('hsm.pkcs11Config.token').querySelector('dd')).toHaveClass('absent')
  })
})

describe('the PKCS#11 module of a provider', () => {
  it('writes what the module did not report muted', () => {
    render(<ModuleSection provider={{ provider_type: 'pkcs11', module_info: { library: 'SoftHSM', manufacturer: 'SoftHSM', library_version: '2.6' } }} fips={false} />)
    expect(row('hsm.module.library').querySelector('dd.v')).toHaveTextContent('SoftHSM')
    expect(row('hsm.module.firmwareVersion').querySelector('dd')).toHaveClass('absent')
  })
})
