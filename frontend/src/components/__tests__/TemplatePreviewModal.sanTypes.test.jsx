/**
 * The SAN preview reads the template's extensions_template.san_types, the field
 * the form saves and issuance enforces when enforce_san_types is on; an empty
 * list, or a template that does not enforce them, allows every type.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { TemplatePreviewModal } from '../TemplatePreviewModal'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key, i18n: { language: 'en' } }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

const preview = (extensions_template, enforce_san_types = true) =>
  render(<TemplatePreviewModal open onClose={() => {}}
                               template={{ name: 'T', extensions_template, enforce_san_types }} />)

describe('TemplatePreviewModal SAN types', () => {
  it('shows a sample per allowed type', () => {
    preview({ san_types: ['email', 'upn'] })
    expect(screen.getByText(/Email: admin@example\.com/)).toBeInTheDocument()
    expect(screen.getByText(/UPN: user@example\.com/)).toBeInTheDocument()
    expect(screen.queryByText(/DNS: /)).not.toBeInTheDocument()
  })

  it('reads a JSON-encoded column too', () => {
    preview(JSON.stringify({ san_types: ['dns'] }))
    expect(screen.getByText(/DNS: server\.example\.com/)).toBeInTheDocument()
  })

  it('says every type is allowed when none is checked', () => {
    preview({ san_types: [] })
    expect(screen.getByText('templates.sanTypesAny')).toBeInTheDocument()
  })

  it('says every type is allowed when the template does not enforce them', () => {
    preview({ san_types: ['dns'] }, false)
    expect(screen.getByText('templates.sanTypesAny')).toBeInTheDocument()
    expect(screen.queryByText(/DNS: /)).not.toBeInTheDocument()
  })
})
