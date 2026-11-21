/**
 * The import dialog in the mockup's vocabulary, with no panel left to the product's own styles:
 * files as « Choisir un fichier… » and a record list, the PEM in a monospace field, the analysis as
 * record lists, pills and notices, the result as sections, the steps ending on the dialog's actions.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, o) => (o && o.count !== undefined ? `${key}:${o.count}` : o && o.name ? `${key}:${o.name}` : key) }),
  initReactI18next: { type: '3rdParty', init: () => {} },
  Trans: ({ children }) => children,
}))
vi.mock('../../contexts/NotificationContext', () => ({ useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn() }) }))
const post = vi.hoisted(() => vi.fn())
vi.mock('../../services', () => ({ apiClient: { post } }))

import { SmartImportModal } from '../SmartImport'

const PEM = '-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----'
const OBJECTS = [
  { type: 'certificate', index: 0, subject: 'CN=leaf', issuer: 'CN=ca', is_ca: false, matched_key_index: 1, key_algorithm: 'RSA', key_size: 2048 },
  { type: 'private_key', index: 1, matched_key_index: null, is_encrypted: true },
]
const productDrawn = (root) => root.querySelector('[class*="space-y"],[class*="text-sm"],[class*="text-xs"],[class*="rounded"],[class*="border-"],.ui-notice')
const file = (text, name) => { const f = new File([text], name); f.arrayBuffer = async () => new TextEncoder().encode(text).buffer; return f }

describe('SmartImport in the mockup\'s vocabulary', () => {
  it('takes files and PEM in mockup fields, then ends on the dialog\'s actions', async () => {
    render(<SmartImportModal isOpen onClose={vi.fn()} />)
    const dialog = screen.getByTestId('smart-import-dialog')
    const pick = dialog.querySelector('label.text-link input[type="file"]')
    expect(pick).toHaveClass('sr-only')
    expect(pick).toHaveAttribute('multiple')
    fireEvent.change(pick, { target: { files: [file(PEM, 'leaf.pem')] } })
    const row = await within(dialog).findByText('leaf.pem')
    expect(row.closest('ul.record-list')).toBeTruthy()
    expect(within(row.closest('li')).getByRole('button', { name: 'common.remove' })).toBeTruthy()
    expect(screen.getByPlaceholderText('import.pastePemPlaceholder')).toHaveClass('mono')
    const actions = dialog.querySelector('.modal-actions')
    expect(within(actions).getByRole('button', { name: 'import.analyze' })).toHaveClass('btn', 'primary')
    expect(productDrawn(dialog)).toBeNull()
  })

  it('shows the analysis as record lists, pills and notices, and the result as sections', async () => {
    post.mockImplementation(async (url) => (url === '/import/analyze'
      ? { data: { objects: OBJECTS, chains: [{ chain_length: 2, is_complete: false, errors: ['gap'], leaf: { subject: 'CN=leaf' } }], matching: { matched_pairs: [[0, 1]] }, validation: { warnings: ['weak'] } } }
      : { data: { certificates_imported: 1, keys_matched: 1, errors: ['one failed'], warnings: [] } }))
    render(<SmartImportModal isOpen onClose={vi.fn()} />)
    const dialog = screen.getByTestId('smart-import-dialog')
    fireEvent.change(screen.getByPlaceholderText('import.pastePemPlaceholder'), { target: { value: PEM } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'import.analyze' }))
    const leaf = await within(dialog).findByText('CN=leaf', { selector: 'label' })
    const card = leaf.closest('li')
    expect(card.closest('ul.record-list')).toBeTruthy()
    expect(within(card).getByRole('checkbox')).toBeChecked()
    expect(card.querySelector('.badge')).toHaveTextContent('import.typeCertificate')
    fireEvent.click(within(card).getByRole('button', { name: 'common.details' }))
    expect(card.querySelector('dl.props')).toHaveTextContent('CN=ca')
    expect([...dialog.querySelectorAll('.notice.warn')].map((n) => n.textContent)).toEqual(['gap', 'weak'])
    expect(within(dialog).getByText('import.chain 1').closest('ul.record-list')).toBeTruthy()
    expect(productDrawn(dialog)).toBeNull()
    fireEvent.click(within(dialog.querySelector('.modal-actions')).getByRole('button', { name: 'import.importObjects:2' }))
    await waitFor(() => expect(within(dialog).getByRole('heading', { name: 'import.importComplete' })).toHaveClass('section-title'))
    expect(dialog.querySelector('.notice.bad')).toHaveTextContent('one failed')
    expect(within(dialog.querySelector('.modal-actions')).getByRole('button', { name: 'common.done' })).toHaveClass('primary')
    expect(productDrawn(dialog)).toBeNull()
  })
})
