/**
 * Smart Import result: a cross-certificate attached to a held root is a success, one left out is reported (#400).
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, vars) => (vars?.count !== undefined ? `${key}:${vars.count}` : key) }),
}))

import { ImportResultStep } from '../SmartImport'

const show = (result) => render(<ImportResultStep importResult={result} onReset={() => {}} onDone={() => {}} />)

describe('ImportResultStep cross-certificates', () => {
  it('reports an attached cross-certificate as imported', () => {
    show({ cas_imported: 0, warning_details: [{ code: 'cross_certificate_attached' }], warnings: [], errors: [] })
    expect(screen.getByText('import.importComplete')).toBeInTheDocument()
    expect(screen.getByTestId('cross-attached').textContent).toContain('import.crossAttached:1')
    expect(screen.queryByText('import.noObjectsImported')).toBeNull()
  })

  it('reports a skipped cross-certificate without calling it imported', () => {
    show({ cas_imported: 0, warning_details: [{ code: 'cross_certificate_skipped' }, { code: 'cross_certificate_skipped' }], warnings: [], errors: [] })
    expect(screen.getByText('import.noObjectsImported')).toBeInTheDocument()
    expect(screen.getByTestId('cross-skipped').textContent).toContain('import.crossSkipped:2')
    expect(screen.queryByTestId('cross-attached')).toBeNull()
  })

  it('shows neither line for an ordinary import', () => {
    show({ cas_imported: 1, warning_details: [], warnings: [], errors: [] })
    expect(screen.queryByTestId('cross-attached')).toBeNull()
    expect(screen.queryByTestId('cross-skipped')).toBeNull()
  })
})
