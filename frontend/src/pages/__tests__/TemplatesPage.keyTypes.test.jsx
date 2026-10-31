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

const keyTypes = () => within(screen.getByLabelText('common.keyType')).getAllByRole('option').map(o => o.value)

describe('TemplateForm key types', () => {
  it('offers no ML-DSA key', () => {
    render(<TemplateForm template={null} onSubmit={() => {}} onCancel={() => {}} />)
    expect(keyTypes()).toContain('RSA-2048')
    expect(keyTypes().filter(l => l.startsWith('ML-DSA'))).toEqual([])
  })
})
