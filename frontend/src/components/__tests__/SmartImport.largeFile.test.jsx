/** A large binary file is read in blocks and listed; a file that cannot be read is named in an error. */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

const notify = vi.hoisted(() => ({ showSuccess: vi.fn(), showError: vi.fn() }))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, values) => (values?.name ? `${key}:${values.name}` : key) }),
  initReactI18next: { type: '3rdParty', init: () => {} },
  Trans: ({ children }) => children,
}))
vi.mock('../../contexts/NotificationContext', () => ({ useNotification: () => notify }))
vi.mock('../../services', () => ({ apiClient: { post: vi.fn() } }))

import { SmartImportModal } from '../SmartImport'

const dropped = (files) => ({ dataTransfer: { types: ['Files'], files } })
const binary = (size, name) => {
  const bytes = new Uint8Array(size).map((_, i) => (i * 7 + 0x30) & 0xff)
  const f = new File([bytes], name)
  f.arrayBuffer = async () => bytes.buffer
  return f
}

describe('SmartImport file reading', () => {
  it('lists a DER file larger than the engine argument limit', async () => {
    render(<SmartImportModal isOpen onClose={vi.fn()} />)
    const dialog = screen.getByTestId('smart-import-dialog')
    fireEvent.drop(dialog.querySelector('.drop-zone').closest('.field'), dropped([binary(300000, 'roots.p7b')]))
    expect(await within(dialog).findByText('roots.p7b')).toBeTruthy()
    expect(notify.showError).not.toHaveBeenCalled()
  })

  it('names a file it could not read', async () => {
    render(<SmartImportModal isOpen onClose={vi.fn()} />)
    const dialog = screen.getByTestId('smart-import-dialog')
    const broken = new File(['x'], 'broken.der')
    broken.arrayBuffer = async () => { throw new Error('gone') }
    fireEvent.drop(dialog.querySelector('.drop-zone').closest('.field'), dropped([broken]))
    await vi.waitFor(() => expect(notify.showError).toHaveBeenCalledWith('import.readFailed:broken.der'))
  })
})
