/** Template form: editing keeps extensions_template keys it has no field for. */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import './pageRenderingSetup.jsx'

vi.mock('../../services/eku.service', () => ({
  ekuService: { getKnown: vi.fn().mockResolvedValue({ data: { ekus: [] } }) },
}))

import { TemplateForm } from '../TemplatesPage'

const template = {
  id: 9, name: 'Qualified', template_type: 'client_auth', key_type: 'RSA-2048', digest: 'sha256', validity_days: 365,
  dn_template: {},
  extensions_template: {
    key_usage: ['digitalSignature'], extended_key_usage: [], san_types: ['email'],
    future_extension: { keep: true },
    qc_statements: { compliance: true, type: 'esign', pds: [{ url: 'https://pki.example/pds_en.pdf', language: 'en' }] },
    certificate_policies: ['0.4.0.194112.1.0'],
  },
}

describe('TemplateForm extensions_template', () => {
  it('submits unknown keys, qc_statements and policy OIDs unchanged', async () => {
    const onSubmit = vi.fn()
    render(<TemplateForm template={template} onSubmit={onSubmit} onCancel={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: 'common.update' }))
    await waitFor(() => expect(onSubmit).toHaveBeenCalled())
    const ext = onSubmit.mock.calls[0][0].extensions_template
    expect(ext.future_extension).toEqual({ keep: true })
    expect(ext.qc_statements).toEqual(template.extensions_template.qc_statements)
    expect(ext.certificate_policies).toEqual(['0.4.0.194112.1.0'])
  })

  it('shows the QcCompliance legal warning', () => {
    render(<TemplateForm template={null} onSubmit={() => {}} onCancel={() => {}} />)
    expect(screen.getByText('templates.qc.legalWarning')).toBeTruthy()
  })
})
