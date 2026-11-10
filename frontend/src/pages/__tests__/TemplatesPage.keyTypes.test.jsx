/**
 * Template form key types come from the key algorithm registry. The digest is the
 * issuing CA's hash, so an ML-DSA template still shows and submits it.
 */
import { afterEach, describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import './pageRenderingSetup.jsx'
import { GROUP_PQ, KEY_ALGORITHMS, isBrainpool, listAlgorithms } from '../../lib/keyAlgorithms'
import { apiClient } from '../../services/apiClient'

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

const allKeyOptions = () => [...screen.getByLabelText('common.keyType').querySelectorAll('option')].map(o => o.value)
// The algorithms offered, without the empty "server default" entry
const keyOptions = () => allKeyOptions().filter(Boolean)
const submit = async (onSubmit, name) => {
  fireEvent.click(screen.getByRole('button', { name }))
  await waitFor(() => expect(onSubmit).toHaveBeenCalled())
  return onSubmit.mock.calls[0][0]
}

// The server's effective policy, as the form reads it
function serverReports(effective) {
  apiClient.get.mockImplementation((url) => Promise.resolve(
    { data: String(url).startsWith('/policies/effective') ? effective : [] }))
}

// Lets a test see the form once the registry generates ML-DSA keys
function generatePq() {
  const saved = PQ_ROWS.map(a => a.generate)
  PQ_ROWS.forEach(a => { a.generate = true })
  return () => PQ_ROWS.forEach((a, i) => { a.generate = saved[i] })
}

describe('TemplateForm key types', () => {
  let restore = () => {}
  afterEach(() => {
    restore(); restore = () => {}
    apiClient.get.mockReset(); apiClient.get.mockResolvedValue({ data: [] })
  })

  it('has ML-DSA rows to offer', () => {
    expect(PQ_ROWS.map(a => a.label)).toContain(PQ_LABEL)
  })

  it('starts a new template on the server default key, with SHA-256', async () => {
    const onSubmit = vi.fn()
    render(<TemplateForm template={null} onSubmit={onSubmit} onCancel={() => {}} />)
    expect(allKeyOptions()[0]).toBe('')
    expect(keyOptions()).toEqual(listAlgorithms({ generate: true }).map(a => a.label))
    expect(screen.getByLabelText('common.keyType')).toHaveValue('')
    fireEvent.change(screen.getByPlaceholderText('templates.namePlaceholder'), { target: { value: 'New' } })
    const body = await submit(onSubmit, 'common.create')
    expect(body).not.toHaveProperty('key_type')
    expect(body.digest).toBe('sha256')
  })

  it('submits the key the operator picks on a new template', async () => {
    const onSubmit = vi.fn()
    render(<TemplateForm template={null} onSubmit={onSubmit} onCancel={() => {}} />)
    const pick = listAlgorithms({ generate: true })[1].label
    fireEvent.change(screen.getByLabelText('common.keyType'), { target: { value: pick } })
    fireEvent.change(screen.getByPlaceholderText('templates.namePlaceholder'), { target: { value: 'New' } })
    expect((await submit(onSubmit, 'common.create')).key_type).toBe(pick)
  })

  it('keeps an ML-DSA template on its key and lets its CA digest be changed', async () => {
    const onSubmit = vi.fn()
    render(<TemplateForm template={template(PQ_LABEL)} onSubmit={onSubmit} onCancel={() => {}} />)
    expect(screen.getByLabelText('common.keyType')).toHaveValue(PQ_LABEL)
    fireEvent.change(screen.getByLabelText('common.digest'), { target: { value: 'sha384' } })
    const body = await submit(onSubmit, 'common.update')
    expect(body.key_type).toBe(PQ_LABEL)
    expect(body.digest).toBe('sha384')
  })

  it('offers every ML-DSA level once generated, and switching to one keeps the digest', async () => {
    restore = generatePq()
    const onSubmit = vi.fn()
    render(<TemplateForm template={template('RSA-2048')} onSubmit={onSubmit} onCancel={() => {}} />)
    expect(keyOptions()).toEqual(expect.arrayContaining(PQ_ROWS.map(a => a.label)))
    expect(screen.getByLabelText('common.digest')).toHaveValue('sha256')
    fireEvent.change(screen.getByLabelText('common.keyType'), { target: { value: PQ_LABEL } })
    expect(screen.getByLabelText('common.keyType')).toHaveValue(PQ_LABEL)
    expect(screen.getByLabelText('common.digest')).toHaveValue('sha256')
    const body = await submit(onSubmit, 'common.update')
    expect(body.key_type).toBe(PQ_LABEL)
    expect(body.digest).toBe('sha256')
  })

  it('offers no ML-DSA or Brainpool key in FIPS mode', async () => {
    serverReports({ fips: true })
    render(<TemplateForm template={template('RSA-2048')} onSubmit={vi.fn()} onCancel={() => {}} />)
    await waitFor(() => expect(keyOptions()).not.toContain(PQ_LABEL))
    expect(keyOptions()).toEqual(listAlgorithms({ generate: true, fips: true }).map(a => a.label))
    expect(keyOptions().some(isBrainpool)).toBe(false)
  })

  it('keeps an ML-DSA template on its key in FIPS mode', async () => {
    serverReports({ fips: true })
    render(<TemplateForm template={template(PQ_LABEL)} onSubmit={vi.fn()} onCancel={() => {}} />)
    await waitFor(() => expect(keyOptions()).not.toContain(PQ_ROWS[0].label))
    expect(keyOptions()).toContain(PQ_LABEL)
    expect(screen.getByLabelText('common.keyType')).toHaveValue(PQ_LABEL)
  })

  it('offers no ML-DSA key on a build without it', async () => {
    serverReports({ ml_dsa: false })
    render(<TemplateForm template={template('RSA-2048')} onSubmit={vi.fn()} onCancel={() => {}} />)
    await waitFor(() => expect(keyOptions()).not.toContain(PQ_LABEL))
    expect(keyOptions()).toEqual(listAlgorithms({ generate: true }).filter(a => a.group !== GROUP_PQ).map(a => a.label))
  })
})
