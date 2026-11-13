/**
 * Common name pattern of a template: the variables of its kind, the non-unique warning, the
 * payload, and literal braces through the real English strings (i18next reads {{x}} itself).
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import i18next from 'i18next'
import en from '../../i18n/locales/en.json'

const real = i18next.createInstance()
await real.init({ lng: 'en', resources: { en: { translation: en } }, interpolation: { escapeValue: false } })

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, values) => real.t(key, values), i18n: { language: 'en', on: vi.fn(), off: vi.fn() } }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

vi.mock('../../services/apiClient', () => {
  const answer = () => Promise.resolve({ data: [] })
  return {
    apiClient: { get: vi.fn(answer), post: vi.fn(answer), put: vi.fn(answer), delete: vi.fn(answer),
      patch: vi.fn(answer), upload: vi.fn(answer), request: vi.fn(answer), setCsrfToken: vi.fn(), clearCsrfToken: vi.fn() },
    buildQueryString: vi.fn().mockReturnValue(''),
    createCRUDService: () => ({ getAll: vi.fn(answer), getById: vi.fn(answer), create: vi.fn(answer),
      update: vi.fn(answer), delete: vi.fn(answer) }),
  }
})

vi.mock('../../services/eku.service', () => ({
  ekuService: { getKnown: vi.fn().mockResolvedValue({ data: { ekus: [] } }) },
}))

import { TemplateForm } from '../TemplatesPage'
import { cnPatternNonUnique, cnPatternSource } from '../../lib/cnPattern'

const template = (fields) => ({
  id: 7, name: 'Patterned', template_type: 'web_server', key_type: 'RSA-2048', digest: 'sha256',
  validity_days: 90, dn_template: {}, extensions_template: { extended_key_usage: ['serverAuth'] }, ...fields,
})

const patternInput = () => screen.getByPlaceholderText('{hostname}-WiFi')

describe('TemplateForm common name pattern', () => {
  it('shows literal braces in its help, not i18next variables', () => {
    render(<TemplateForm template={template({})} onSubmit={vi.fn()} onCancel={() => {}} />)
    const help = screen.getByText(/Write \{\{ or \}\} for a literal brace/)
    expect(help.textContent).toContain('for example {hostname}-WiFi')
  })

  it('lists the variables of a computer template', () => {
    render(<TemplateForm template={template({})} onSubmit={vi.fn()} onCancel={() => {}} />)
    expect(screen.getByTestId('cn-pattern-variables').textContent).toContain('{hostname} {fqdn} {domain} {realm}')
  })

  it('lists the user variables once the subject comes from the directory, none before', () => {
    render(<TemplateForm template={template({ template_type: 'client_auth' })} onSubmit={vi.fn()} onCancel={() => {}} />)
    expect(screen.getByTestId('cn-pattern-unavailable')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText(en.templates.adDerivedSubject))
    expect(screen.getByTestId('cn-pattern-variables').textContent).toContain('{username} {upn} {mail} {displayName}')
  })

  it('warns beside the field that a display name is not unique', () => {
    render(<TemplateForm template={template({ template_type: 'client_auth', ad_derived_subject: true })}
      onSubmit={vi.fn()} onCancel={() => {}} />)
    expect(screen.queryByTestId('cn-pattern-non-unique')).toBeNull()
    fireEvent.change(patternInput(), { target: { value: '{displayName} ({username})' } })
    expect(screen.getByTestId('cn-pattern-non-unique').textContent).toBe(
      '{displayName} may be shared by several accounts: certificates could carry the same CN.')
  })

  it('sends the pattern trimmed and the path option, null once cleared', async () => {
    const onSubmit = vi.fn()
    render(<TemplateForm template={template({ subject_cn_pattern: '{fqdn}' })} onSubmit={onSubmit} onCancel={() => {}} />)
    fireEvent.change(patternInput(), { target: { value: '  {hostname}-WiFi ' } })
    fireEvent.click(screen.getByLabelText(en.templates.cnPatternKeepPath))
    fireEvent.click(screen.getByRole('button', { name: real.t('common.update') }))
    await waitFor(() => expect(onSubmit).toHaveBeenCalled())
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ subject_cn_pattern: '{hostname}-WiFi', subject_cn_keep_path: true })
    fireEvent.change(patternInput(), { target: { value: '   ' } })
    fireEvent.click(screen.getByRole('button', { name: real.t('common.update') }))
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(2))
    expect(onSubmit.mock.calls[1][0].subject_cn_pattern).toBeNull()
  })
})

describe('pattern helpers', () => {
  it('reads the subject source as the backend does', () => {
    expect(cnPatternSource('vpn_client', false)).toBe('machine')
    expect(cnPatternSource('client_auth', true)).toBe('directory')
    expect(cnPatternSource('client_auth', false)).toBe('request')
  })

  it('names non-unique variables, not escaped braces', () => {
    expect(cnPatternNonUnique('{{displayName}} {mail} {username}')).toEqual(['{mail}'])
  })
})
