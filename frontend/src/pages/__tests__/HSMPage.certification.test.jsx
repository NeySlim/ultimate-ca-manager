/** HSM provider form: the declared certification is sent, '' clears it. */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import './pageRenderingSetup.jsx'

import { ProviderModal, HSM_CERTIFICATIONS } from '../HSMPage'

describe('HSM provider form, certification', () => {
  it('sends the stored certification back on save', async () => {
    const onSave = vi.fn()
    render(<ProviderModal provider={{ id: 1, name: 'P', provider_type: 'pkcs11', certification: 'eucc-high' }}
                          hsmStatus={null} onSave={onSave} onClose={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: 'common.save' }))
    await waitFor(() => expect(onSave).toHaveBeenCalled())
    expect(onSave.mock.calls[0][0].certification).toBe('eucc-high')
  })

  it('sends an empty string (clear) for a provider that declares none', async () => {
    const onSave = vi.fn()
    render(<ProviderModal provider={{ id: 2, name: 'P', provider_type: 'pkcs11', certification: null }}
                          hsmStatus={null} onSave={onSave} onClose={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: 'common.save' }))
    await waitFor(() => expect(onSave).toHaveBeenCalled())
    expect(onSave.mock.calls[0][0].certification).toBe('')
  })

  it('offers the five values the server accepts', () => {
    expect(HSM_CERTIFICATIONS).toEqual(['cc-eal4+', 'eucc-high', 'fips-140-3-l3', 'fips-140-2-l3', 'other'])
  })
})
