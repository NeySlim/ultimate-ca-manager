/** The import's file field says it takes dropped files, and marks itself while files are dragged over it. */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
  initReactI18next: { type: '3rdParty', init: () => {} },
  Trans: ({ children }) => children,
}))
vi.mock('../../contexts/NotificationContext', () => ({ useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn() }) }))
vi.mock('../../services', () => ({ apiClient: { post: vi.fn() } }))

import { SmartImportModal } from '../SmartImport'

const PEM = '-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----'
const file = (text, name) => { const f = new File([text], name); f.arrayBuffer = async () => new TextEncoder().encode(text).buffer; return f }
const dragged = (files = []) => ({ dataTransfer: { types: ['Files'], files } })

describe('SmartImport drop zone', () => {
  it('draws a drop hint around the file picker', () => {
    render(<SmartImportModal isOpen onClose={vi.fn()} />)
    const zone = screen.getByTestId('smart-import-dialog').querySelector('.drop-zone')
    expect(zone).toBeTruthy()
    expect(zone).toHaveTextContent('import.dropFileHere')
    expect(zone.querySelector('label.text-link input[type="file"]')).toBeTruthy()
    expect(within(zone).getByText('common.chooseFile')).toBeTruthy()
  })

  it('marks the field while files are dragged over it, and drops them in the list', async () => {
    render(<SmartImportModal isOpen onClose={vi.fn()} />)
    const dialog = screen.getByTestId('smart-import-dialog')
    const field = dialog.querySelector('.drop-zone').closest('.field')
    expect(field).not.toHaveClass('dragover')
    fireEvent.dragEnter(field, dragged())
    fireEvent.dragOver(field, dragged())
    expect(field).toHaveClass('dragover')
    fireEvent.dragLeave(field, dragged())
    expect(field).not.toHaveClass('dragover')
    fireEvent.dragOver(field, dragged())
    fireEvent.drop(field, dragged([file(PEM, 'dropped.pem')]))
    expect(field).not.toHaveClass('dragover')
    expect(await within(dialog).findByText('dropped.pem')).toBeTruthy()
  })
})
