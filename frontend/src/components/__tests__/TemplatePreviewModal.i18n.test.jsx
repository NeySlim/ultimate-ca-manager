/** The template preview names every field through i18n keys. */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { TemplatePreviewModal } from '../TemplatePreviewModal'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, opts) => (opts?.count !== undefined ? `${key}:${opts.count}` : key) }),
}))

describe('TemplatePreviewModal labels', () => {
  it('translates its labels and the fixed CN value', () => {
    render(<TemplatePreviewModal open onClose={() => {}} template={{
      name: 'T', key_type: 'RSA-2048', validity_days: 90, allow_any_cn: false,
      key_usage: ['digitalSignature'], extended_key_usage: ['serverAuth'],
    }} />)
    for (const key of ['templates.commonName', 'templates.template', 'common.keyAlgorithm', 'common.validityPeriod',
      'common.keyUsage', 'common.extKeyUsage', 'common.subjectAltNames']) {
      expect(screen.getByText(key)).toBeInTheDocument()
    }
    // The CN value and the restriction badge
    expect(screen.getAllByText('templates.fixedCN')).toHaveLength(2)
    expect(screen.getByText(/^templates\.validityDays:90 \(/)).toBeInTheDocument()
    for (const literal of ['Key Algorithm', 'Validity Period', 'Fixed by template', /\d+ days/]) {
      expect(screen.queryByText(literal)).toBeNull()
    }
  })

  it("names the key algorithm through the row's i18n key, as the other forms do", () => {
    const { unmount } = render(<TemplatePreviewModal open onClose={() => {}} template={{ name: 'T', key_type: 'RSA-2048' }} />)
    expect(screen.getByText('common.keyTypes.rsa2048')).toBeInTheDocument()
    expect(screen.queryByText('RSA 2048')).toBeNull()
    unmount()
    render(<TemplatePreviewModal open onClose={() => {}} template={{ name: 'T', key_type: 'ML-DSA-65' }} />)
    expect(screen.getByText('common.keyAlgorithmLevel')).toBeInTheDocument()
  })
})
