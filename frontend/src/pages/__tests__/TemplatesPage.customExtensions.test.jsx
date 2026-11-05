/** #437: the template form keeps, edits and validates custom extensions. */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import './pageRenderingSetup.jsx'

vi.mock('../../services/eku.service', () => ({
  ekuService: { getKnown: vi.fn().mockResolvedValue({ data: { ekus: [] } }) },
}))

import { TemplateForm } from '../TemplatesPage'

const template = {
  id: 7, name: 'Custom', template_type: 'custom', key_type: 'RSA-2048', digest: 'sha256', validity_days: 365,
  dn_template: {}, extensions_template: { key_usage: ['digitalSignature'] },
  custom_extensions: [{ oid: '1.3.6.1.4.1.99999.1', critical: true, value: '0500' }],
}

describe('TemplateForm custom extensions', () => {
  it('submits the stored list back, then an edited one', async () => {
    const onSubmit = vi.fn()
    render(<TemplateForm template={template} onSubmit={onSubmit} onCancel={() => {}} />)
    expect(screen.getByTestId('custom-extensions-critical-warning')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'common.update' }))
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1))
    expect(onSubmit.mock.calls[0][0].custom_extensions).toEqual(template.custom_extensions)

    fireEvent.change(screen.getByDisplayValue('0500'), { target: { value: '02:01:01' } })
    fireEvent.click(screen.getByRole('button', { name: 'common.update' }))
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(2))
    expect(onSubmit.mock.calls[1][0].custom_extensions).toEqual(
      [{ oid: '1.3.6.1.4.1.99999.1', critical: true, value: '020101' }])
  })

  it('will not submit an invalid row', async () => {
    const onSubmit = vi.fn()
    render(<TemplateForm template={template} onSubmit={onSubmit} onCancel={() => {}} />)
    fireEvent.change(screen.getByDisplayValue('0500'), { target: { value: '050' } })
    const submit = screen.getByRole('button', { name: 'common.update' })
    expect(submit.disabled).toBe(true)
    fireEvent.submit(submit.closest('form'))
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('a new template sends an empty list', async () => {
    const onSubmit = vi.fn()
    render(<TemplateForm template={null} onSubmit={onSubmit} onCancel={() => {}} />)
    fireEvent.change(screen.getByPlaceholderText('templates.namePlaceholder'), { target: { value: 'New' } })
    fireEvent.click(screen.getByRole('button', { name: 'common.create' }))
    await waitFor(() => expect(onSubmit).toHaveBeenCalled())
    expect(onSubmit.mock.calls[0][0].custom_extensions).toEqual([])
  })

  it('says when the stored list cannot be applied', () => {
    render(<TemplateForm template={{ ...template, custom_extensions: [], custom_extensions_error: 'custom_extensions is not valid JSON' }}
      onSubmit={() => {}} onCancel={() => {}} />)
    const banner = screen.getByTestId('custom-extensions-stored-error')
    expect(banner.textContent).toContain('customExtensions.storedInvalid')
    expect(banner.textContent).toContain('custom_extensions is not valid JSON')
  })

  it('shows no such warning for a valid list', () => {
    render(<TemplateForm template={template} onSubmit={() => {}} onCancel={() => {}} />)
    expect(screen.queryByTestId('custom-extensions-stored-error')).toBeNull()
  })
})
