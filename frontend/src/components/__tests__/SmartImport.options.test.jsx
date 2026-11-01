/**
 * Smart import options: every checkbox reaches the execute request, CSRs included,
 * with the positions of the objects left selected.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
  initReactI18next: { type: '3rdParty', init: () => {} },
  Trans: ({ children }) => children,
}))

vi.mock('../../contexts/NotificationContext', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn() }),
}))

const post = vi.hoisted(() => vi.fn())
vi.mock('../../services', () => ({ apiClient: { post } }))

import { SmartImportWidget } from '../SmartImport'

const OBJECTS = [
  { type: 'certificate', index: 0, subject: 'CN=a', is_ca: false },
  { type: 'csr', index: 100, subject: 'CN=b' },
]

describe('smart import options', () => {
  it('sends import_csrs and the selected positions', async () => {
    post.mockImplementation(async (url) => (url === '/import/analyze'
      ? { data: { objects: OBJECTS, chains: [], matching: {}, validation: {} } }
      : { data: { success: true, errors: [], warnings: [] } }))
    render(<SmartImportWidget />)
    fireEvent.change(screen.getByPlaceholderText('import.pastePemPlaceholder'),
      { target: { value: '-----BEGIN CERTIFICATE-----' } })
    fireEvent.click(screen.getByRole('button', { name: 'import.analyze' }))
    fireEvent.click(await screen.findByLabelText('import.importCSRs'))
    fireEvent.click(screen.getByRole('button', { name: 'import.importObjects' }))
    await waitFor(() => expect(post).toHaveBeenCalledWith('/import/execute', expect.anything()))
    const { options } = post.mock.calls.find(([url]) => url === '/import/execute')[1]
    expect(options.import_csrs).toBe(false)
    expect(options.selected_indices).toEqual([0, 1])
  })
})
