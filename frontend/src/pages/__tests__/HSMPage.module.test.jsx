/** HSM details: the PKCS#11 module section, for every provider the PKCS#11 driver serves. */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import './pageRenderingSetup.jsx'

import { ModuleSection } from '../HSMPage'

const MODULE = { library: 'Vendor PKCS#11', manufacturer: 'Vendor', library_version: '5.1', firmware_version: '7.2' }

describe('HSM details, PKCS#11 module', () => {
  it.each(['pkcs11', 'aws-cloudhsm'])('is shown for a %s provider', (type) => {
    render(<ModuleSection provider={{ provider_type: type, module_info: MODULE }} fips={false} />)
    expect(screen.getByText('hsm.module.title')).toBeTruthy()
    expect(screen.getByText('Vendor PKCS#11')).toBeTruthy()
  })

  it('is not shown for a cloud key vault', () => {
    const { container } = render(<ModuleSection provider={{ provider_type: 'azure-keyvault' }} fips={false} />)
    expect(container.textContent).toBe('')
  })

  it('warns about SoftHSM in FIPS mode only', () => {
    const provider = { provider_type: 'pkcs11', softhsm: true, module_info: null }
    const { rerender } = render(<ModuleSection provider={provider} fips={false} />)
    expect(screen.queryByText('hsm.module.softhsmFips')).toBeNull()
    rerender(<ModuleSection provider={provider} fips />)
    expect(screen.getByText('hsm.module.softhsmFips')).toBeTruthy()
  })
})
