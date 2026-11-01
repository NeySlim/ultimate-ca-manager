/** HSM key generation reads its asymmetric algorithms from the key registry, per provider type. */
import { describe, it, expect, vi } from 'vitest'
import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react'
import './pageRenderingSetup.jsx'
import { GROUP_PQ, KEY_ALGORITHMS, listAlgorithms } from '../../lib/keyAlgorithms'
import { apiClient } from '../../services/apiClient'

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

  it('names the AES group through i18n', () => {
    renderModal('pkcs11')
    const aes = Array.from(screen.getByLabelText('common.keyType').options).find(o => o.value === 'aes')
    expect(aes.textContent).toBe('common.keyGroups.aes')
  })

  // The registry rows name the HSM types that hold ML-DSA; the modal adds no rule of its own
  const PQ_LABELS = KEY_ALGORITHMS.filter(a => a.group === GROUP_PQ).map(a => a.label)
  const holders = PROVIDERS.filter(p => listAlgorithms({ generate: true, provider: p }).some(a => a.group === GROUP_PQ))

  it('names PKCS#11, OpenBao and Google Cloud KMS as the ML-DSA holders', () => {
    expect(holders).toEqual(['pkcs11', 'openbao', 'google-kms'])
  })

  it.each(['pkcs11', 'openbao', 'google-kms'])('offers the three ML-DSA levels on %s and sends the label', async (type) => {
    const onSave = renderModal(type)
    fireEvent.change(screen.getByLabelText('common.keyType'), { target: { value: GROUP_PQ } })
    expect(offered(screen.getByLabelText('common.keySize'))).toEqual(PQ_LABELS)
    fireEvent.change(screen.getByLabelText('common.keySize'), { target: { value: 'ML-DSA-87' } })
    expect((await save(onSave)).algorithm).toBe('ML-DSA-87')
  })

  it('says ML-DSA on Google Cloud KMS is untested, and only there', () => {
    for (const type of ['google-kms', 'pkcs11']) {
      renderModal(type)
      fireEvent.change(screen.getByLabelText('common.keyType'), { target: { value: GROUP_PQ } })
      expect(screen.queryAllByText('hsm.mldsaUntestedGoogleKms')).toHaveLength(type === 'google-kms' ? 1 : 0)
      fireEvent.change(screen.getByLabelText('common.keyType'), { target: { value: 'rsa' } })
      expect(screen.queryByText('hsm.mldsaUntestedGoogleKms')).toBeNull()
      cleanup()
    }
  })

  it.each(['azure-keyvault', 'aws-cloudhsm'])('offers no ML-DSA key on %s', (type) => {
    renderModal(type)
    expect(offered(screen.getByLabelText('common.keyType'))).not.toContain(GROUP_PQ)
  })

  it.each([['on a build without it', { ml_dsa: false }], ['in FIPS mode', { fips: true }]])(
    'offers no ML-DSA key %s', async (_name, effective) => {
      apiClient.get.mockImplementation((url) => Promise.resolve(
        { data: String(url).startsWith('/policies/effective') ? effective : [] }))
      try {
        renderModal('pkcs11')
        await waitFor(() => expect(offered(screen.getByLabelText('common.keyType'))).not.toContain(GROUP_PQ))
        expect(offered(screen.getByLabelText('common.keyType'))).toContain('rsa')
      } finally {
        apiClient.get.mockReset(); apiClient.get.mockResolvedValue({ data: [] })
      }
    })

  it('moves an ML-DSA choice made before the policy answer to the first key offered', async () => {
    let answer
    apiClient.get.mockImplementation((url) => (String(url).startsWith('/policies/effective')
      ? new Promise((resolve) => { answer = resolve })
      : Promise.resolve({ data: [] })))
    try {
      const onSave = renderModal('pkcs11')
      fireEvent.change(screen.getByLabelText('common.keyType'), { target: { value: GROUP_PQ } })
      fireEvent.change(screen.getByLabelText('common.keySize'), { target: { value: 'ML-DSA-65' } })
      await waitFor(() => expect(answer).toBeTypeOf('function'))
      answer({ data: { fips: true } })
      await waitFor(() => expect(offered(screen.getByLabelText('common.keyType'))).not.toContain(GROUP_PQ))
      const first = listAlgorithms({ generate: true, provider: 'pkcs11', fips: true })[0]
      await waitFor(() => expect(screen.getByLabelText('common.keyType')).toHaveValue(first.group))
      expect((await save(onSave)).algorithm).toBe(first.label)
    } finally {
      apiClient.get.mockReset(); apiClient.get.mockResolvedValue({ data: [] })
    }
  })
})
