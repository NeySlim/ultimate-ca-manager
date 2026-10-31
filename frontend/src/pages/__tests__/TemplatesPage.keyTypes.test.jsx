/**
 * Template form key types come from the key algorithm registry: an ML-DSA
 * template keeps its key, shows no digest, and submits the registry label.
 */
import { afterEach, describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import './pageRenderingSetup.jsx'
import { GROUP_PQ, KEY_ALGORITHMS, findAlgorithm, listAlgorithms } from '../../lib/keyAlgorithms'

vi.mock('../../services/eku.service', () => ({
  ekuService: { getKnown: vi.fn().mockResolvedValue({ data: { ekus: [] } }) },
}))

// A native select exposes the options the real one renders in a portal
vi.mock('../../components', async (orig) => ({
  ...(await orig()),
  Select: ({ label, options = [], value, onChange }) => (
    <select aria-label={label} value={value ?? ''} onChange={(e) => onChange?.(e.target.value)}>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  ),
}))

import { TemplateForm } from '../TemplatesPage'

const PQ_ROWS = KEY_ALGORITHMS.filter(a => a.group === GROUP_PQ)
const PQ_LABEL = PQ_ROWS.find(a => a.label.endsWith('-65'))?.label

const template = (key_type) => ({
  id: 4, name: 'PQ leaf', template_type: 'web_server', key_type, digest: 'sha256', validity_days: 90,
  dn_template: {}, extensions_template: { key_usage: ['digitalSignature'], extended_key_usage: ['serverAuth'], san_types: ['dns'] },
})

const keyOptions = () => [...screen.getByLabelText('common.keyType').querySelectorAll('option')].map(o => o.value)
const submit = async (onSubmit, name) => {
  fireEvent.click(screen.getByRole('button', { name }))
  await waitFor(() => expect(onSubmit).toHaveBeenCalled())
  return onSubmit.mock.calls[0][0]
}

// Lets a test see the form once the registry generates ML-DSA keys
function generatePq() {
  const saved = PQ_ROWS.map(a => a.generate)
  PQ_ROWS.forEach(a => { a.generate = true })
  return () => PQ_ROWS.forEach((a, i) => { a.generate = saved[i] })
}

describe('TemplateForm key types', () => {
  let restore = () => {}
  afterEach(() => { restore(); restore = () => {} })

  it('has ML-DSA rows to offer', () => {
    expect(PQ_ROWS.map(a => a.label)).toContain(PQ_LABEL)
  })

  it('defaults a new template to the first generated key and its digest', async () => {
    const onSubmit = vi.fn()
    render(<TemplateForm template={null} onSubmit={onSubmit} onCancel={() => {}} />)
    const first = listAlgorithms({ generate: true })[0]
    expect(keyOptions()).toEqual(listAlgorithms({ generate: true }).map(a => a.label))
    fireEvent.change(screen.getByPlaceholderText('templates.namePlaceholder'), { target: { value: 'New' } })
    const body = await submit(onSubmit, 'common.create')
    expect(body.key_type).toBe(first.label)
    expect(body.digest).toBe(first.digest)
  })

  it('keeps an ML-DSA template on its key and hides the digest', async () => {
    const onSubmit = vi.fn()
    render(<TemplateForm template={template(PQ_LABEL)} onSubmit={onSubmit} onCancel={() => {}} />)
    expect(screen.getByLabelText('common.keyType')).toHaveValue(PQ_LABEL)
    expect(screen.queryByLabelText('common.digest')).toBeNull()
    const body = await submit(onSubmit, 'common.update')
    expect(body.key_type).toBe(PQ_LABEL)
    expect(body).not.toHaveProperty('digest')
  })

  it('offers every ML-DSA level once generated, and switching to one drops the digest', async () => {
    restore = generatePq()
    const onSubmit = vi.fn()
    render(<TemplateForm template={template('RSA-2048')} onSubmit={onSubmit} onCancel={() => {}} />)
    expect(keyOptions()).toEqual(expect.arrayContaining(PQ_ROWS.map(a => a.label)))
    expect(screen.getByLabelText('common.digest')).toHaveValue('sha256')
    fireEvent.change(screen.getByLabelText('common.keyType'), { target: { value: PQ_LABEL } })
    expect(screen.getByLabelText('common.keyType')).toHaveValue(PQ_LABEL)
    expect(screen.queryByLabelText('common.digest')).toBeNull()
    const body = await submit(onSubmit, 'common.update')
    expect(body.key_type).toBe(PQ_LABEL)
    expect(body).not.toHaveProperty('digest')
  })

  it('shows the digest again for a key that takes one', async () => {
    render(<TemplateForm template={template(PQ_LABEL)} onSubmit={() => {}} onCancel={() => {}} />)
    fireEvent.change(screen.getByLabelText('common.keyType'), { target: { value: 'EC-P384' } })
    expect(findAlgorithm('EC-P384').digest).toBeTruthy()
    expect(screen.getByLabelText('common.digest')).toBeTruthy()
  })
})
