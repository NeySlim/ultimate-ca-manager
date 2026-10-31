/** Template form key types: no ML-DSA while the form always sends a digest. */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import './pageRenderingSetup.jsx'

vi.mock('../../services/eku.service', () => ({
  ekuService: { getKnown: vi.fn().mockResolvedValue({ data: { ekus: [] } }) },
}))

vi.mock('../../components', async (importOriginal) => ({
  ...(await importOriginal()),
  Select: ({ label, options = [], value, onChange }) => (
    <select aria-label={label} value={value ?? ''} onChange={(e) => onChange?.(e.target.value)}>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  ),
}))

import { TemplateForm } from '../TemplatesPage'
import { KEY_ALGORITHMS } from '../../lib/keyAlgorithms'

// Generated keys that sign without a digest, read from the registry
const NO_DIGEST = KEY_ALGORITHMS.filter(a => a.generate && a.digest === null).map(a => a.label)

const keyTypes = () => within(screen.getByLabelText('common.keyType')).getAllByRole('option').map(o => o.value)

describe('TemplateForm key types', () => {
  it('offers no ML-DSA key', () => {
    render(<TemplateForm template={null} onSubmit={() => {}} onCancel={() => {}} />)
    expect(NO_DIGEST).toContain('ML-DSA-65')
    expect(keyTypes()).toContain('RSA-2048')
    expect(keyTypes().filter(l => NO_DIGEST.includes(l))).toEqual([])
  })

  it("keeps an existing template's ML-DSA key and offers no other", () => {
    render(<TemplateForm template={{ name: 'pq', key_type: 'ML-DSA-65' }} onSubmit={() => {}} onCancel={() => {}} />)
    expect(screen.getByLabelText('common.keyType').value).toBe('ML-DSA-65')
    expect(keyTypes().filter(l => NO_DIGEST.includes(l))).toEqual(['ML-DSA-65'])
  })
})
