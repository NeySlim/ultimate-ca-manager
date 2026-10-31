/** HSM key generation reads its asymmetric algorithms from the key registry, per provider type. */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import './pageRenderingSetup.jsx'
import { GROUP_PQ, KEY_ALGORITHMS, listAlgorithms } from '../../lib/keyAlgorithms'

// ML-DSA rows made generable, one held by PKCS#11: the modal alone must keep the others out
vi.mock('../../lib/keyAlgorithms', async (importOriginal) => {
  const actual = await importOriginal()
  for (const row of actual.KEY_ALGORITHMS.filter(a => a.group === actual.GROUP_PQ)) {
    Object.assign(row, { generate: true, providers: row.label === 'ML-DSA-87' ? ['pkcs11'] : null })
  }
  return actual
})

vi.mock('../../components', async (importOriginal) => ({
  ...(await importOriginal()),
  Input: ({ label, helperText, ...props }) => <input aria-label={label} {...props} />,
  Select: ({ label, value, onChange, options }) => (
    <select aria-label={label} value={value ?? ''} onChange={(e) => onChange(e.target.value)}>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  ),
}))

import { KeyModal } from '../HSMPage'

const PROVIDERS = ['pkcs11', 'openbao', 'azure-keyvault', 'google-kms', 'aws-cloudhsm']
const offered = (select) => Array.from(select.options).map(o => o.value)

function renderModal(providerType) {
  const onSave = vi.fn()
  render(<KeyModal provider={{ id: 1, provider_type: providerType }} onSave={onSave} onClose={() => {}} />)
  fireEvent.change(screen.getByLabelText('hsm.keyLabel'), { target: { value: 'k1' } })
  return onSave
}

async function save(onSave) {
  fireEvent.click(screen.getByRole('button', { name: 'common.generate' }))
  await waitFor(() => expect(onSave).toHaveBeenCalled())
  return onSave.mock.calls[0][0]
}

describe('HSM key generation, from the registry', () => {
  it.each(listAlgorithms({ generate: true, provider: 'pkcs11' }).filter(a => a.group !== GROUP_PQ))(
    'sends $label by its registry label on a PKCS#11 provider', async (row) => {
      const onSave = renderModal('pkcs11')
      fireEvent.change(screen.getByLabelText('common.keyType'), { target: { value: row.group } })
      fireEvent.change(screen.getByLabelText('common.keySize'), { target: { value: row.label } })
      expect((await save(onSave)).algorithm).toBe(row.label)
    })

  it('starts on the first registry key the provider can hold', async () => {
    const onSave = renderModal('openbao')
    const first = listAlgorithms({ generate: true, provider: 'openbao' })[0]
    expect((await save(onSave)).algorithm).toBe(first.label)
  })

  it('keeps Brainpool to the providers its registry row names', () => {
    renderModal('openbao')
    expect(offered(screen.getByLabelText('common.keyType'))).not.toContain('brainpool')
  })

  it('still offers AES, which the key registry does not hold', async () => {
    const onSave = renderModal('pkcs11')
    fireEvent.change(screen.getByLabelText('common.keyType'), { target: { value: 'aes' } })
    fireEvent.change(screen.getByLabelText('common.keySize'), { target: { value: 'AES-256' } })
    expect((await save(onSave)).algorithm).toBe('AES-256')
  })

  it.each(PROVIDERS.filter(p => p !== 'pkcs11'))('offers no ML-DSA key on %s, which no row names', (type) => {
    expect(KEY_ALGORITHMS.find(a => a.label === 'ML-DSA-65')).toMatchObject({ generate: true, providers: null })
    renderModal(type)
    expect(offered(screen.getByLabelText('common.keyType'))).not.toContain(GROUP_PQ)
  })

  it('offers on PKCS#11 only the ML-DSA row that names it', () => {
    renderModal('pkcs11')
    fireEvent.change(screen.getByLabelText('common.keyType'), { target: { value: GROUP_PQ } })
    expect(offered(screen.getByLabelText('common.keySize'))).toEqual(['ML-DSA-87'])
  })
})
