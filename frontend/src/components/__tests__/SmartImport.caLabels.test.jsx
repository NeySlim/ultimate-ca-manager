/**
 * Smart import (#459): each CA kept offers a display name (its CN by default) and a description;
 * only those given reach the execute request, keyed by their analysis position.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

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
  { type: 'certificate', index: 0, subject: 'CN=Leaf,O=Example', is_ca: false },
  { type: 'certificate', index: 1, subject: 'CN=Partner Root,O=Example', is_ca: true },
  { type: 'certificate', index: 2, subject: 'CN=Partner Issuing', is_ca: true },
]

async function preview() {
  post.mockImplementation(async (url) => (url === '/import/analyze'
    ? { data: { objects: OBJECTS, chains: [], matching: {}, validation: {} } }
    : { data: { success: true, errors: [], warnings: [] } }))
  render(<SmartImportWidget />)
  fireEvent.change(screen.getByPlaceholderText('import.pastePemPlaceholder'), { target: { value: '-----BEGIN CERTIFICATE-----' } })
  fireEvent.click(screen.getByRole('button', { name: 'import.analyze' }))
  await screen.findByTestId('import-ca-label-1')
}
const execute = async () => {
  fireEvent.click(screen.getByRole('button', { name: 'import.importObjects' }))
  await waitFor(() => expect(post).toHaveBeenCalledWith('/import/execute', expect.anything()))
  return post.mock.calls.find(([url]) => url === '/import/execute')[1].options
}

describe('smart import: the name and description of a CA', () => {
  beforeEach(() => post.mockReset())

  it('offers them for each CA only, the CN as the default name', async () => {
    await preview()
    expect(screen.queryByTestId('import-ca-label-0')).toBeNull()
    expect(within(screen.getByTestId('import-ca-label-1')).getByRole('textbox', { name: 'cas.label.displayName' }))
      .toHaveAttribute('placeholder', 'Partner Root')
    expect(screen.getByTestId('import-ca-label-2')).toBeInTheDocument()
  })

  it('sends only the labels given, by position', async () => {
    await preview()
    const second = within(screen.getByTestId('import-ca-label-2'))
    fireEvent.change(second.getByRole('textbox', { name: 'cas.label.displayName' }), { target: { value: 'Issuing (partner)' } })
    fireEvent.change(second.getByRole('textbox', { name: 'cas.label.description' }), { target: { value: 'Signed by the partner' } })
    const options = await execute()
    expect(options.ca_labels).toEqual({ 2: { name: 'Issuing (partner)', description: 'Signed by the partner' } })
  })

  it('sends none when nothing was given, nor for a CA left out', async () => {
    await preview()
    fireEvent.change(within(screen.getByTestId('import-ca-label-1')).getByRole('textbox', { name: 'cas.label.displayName' }), { target: { value: 'Dropped' } })
    fireEvent.click(screen.getByLabelText('CN=Partner Root,O=Example'))
    expect(screen.queryByTestId('import-ca-label-1')).toBeNull()
    const options = await execute()
    expect(options).not.toHaveProperty('ca_labels')
  })
})
