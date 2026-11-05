/** #437: the editor adds, edits and removes rows, flags bad ones and warns on critical. */
import { describe, it, expect, vi } from 'vitest'
import { useState } from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import '../../pages/__tests__/pageRenderingSetup.jsx'

import { CustomExtensionsEditor } from '../CustomExtensionsEditor'

function Harness({ initial = [], onRows = () => {} }) {
  const [rows, setRows] = useState(initial)
  return <CustomExtensionsEditor rows={rows} onChange={(r) => { setRows(r); onRows(r) }} />
}

describe('CustomExtensionsEditor', () => {
  it('adds a row and reports an invalid OID and hex', () => {
    const onRows = vi.fn()
    render(<Harness onRows={onRows} />)
    fireEvent.click(screen.getByText('customExtensions.add'))
    fireEvent.change(screen.getByPlaceholderText('1.3.6.1.4.1.99999.1'), { target: { value: '1.2.03' } })
    expect(screen.getByRole('alert').textContent).toBe('customExtensions.invalidOid')
    fireEvent.change(screen.getByPlaceholderText('1.3.6.1.4.1.99999.1'), { target: { value: '1.2.3' } })
    fireEvent.change(screen.getByPlaceholderText('0c0568656c6c6f'), { target: { value: 'abc' } })
    expect(screen.getByRole('alert').textContent).toBe('customExtensions.invalidHex')
    fireEvent.change(screen.getByPlaceholderText('0c0568656c6c6f'), { target: { value: '0500' } })
    expect(screen.queryByRole('alert')).toBeNull()
    expect(onRows).toHaveBeenLastCalledWith([{ oid: '1.2.3', critical: false, value: '0500' }])
  })

  it('warns only while an entry is critical', () => {
    render(<Harness initial={[{ oid: '1.2.3', critical: false, value: '0500' }]} />)
    expect(screen.queryByTestId('custom-extensions-critical-warning')).toBeNull()
    fireEvent.click(screen.getByLabelText('customExtensions.critical'))
    expect(screen.getByTestId('custom-extensions-critical-warning').textContent).toContain('customExtensions.criticalWarning')
    fireEvent.click(screen.getByLabelText('customExtensions.critical'))
    expect(screen.queryByTestId('custom-extensions-critical-warning')).toBeNull()
  })

  it('removes a row', () => {
    const onRows = vi.fn()
    render(<Harness initial={[{ oid: '1.2.3', critical: false, value: '0500' }]} onRows={onRows} />)
    fireEvent.click(screen.getByLabelText('common.remove'))
    expect(onRows).toHaveBeenLastCalledWith([])
  })
})
