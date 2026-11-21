/**
 * The certificate pickers name a certificate the way the list does: its CN, with
 * the description (Rename) alongside when it says something else (#365).
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))


const getAll = vi.fn()
vi.mock('../../services', () => ({
  certificatesService: { getAll: (...a) => getAll(...a) },
}))

import CertificatePickerModal from '../CertificatePickerModal'

const renamed = { id: 7, common_name: 'host.example.com', descr: 'Renamed', key_type: 'EC', has_private_key: true, valid_to: '2099-01-01T00:00:00Z' }
const plain = { id: 8, common_name: 'plain.example.com', descr: 'plain.example.com', has_private_key: true, valid_to: '2099-01-01T00:00:00Z' }


describe('certificate pickers name a certificate by its CN (#365)', () => {
  it('the picker dialog shows the CN with the description under it', async () => {
    getAll.mockResolvedValue({ data: [renamed, plain], meta: { total: 2 } })
    render(<CertificatePickerModal isOpen onClose={vi.fn()} onSelect={vi.fn()} />)
    const name = await screen.findByText('host.example.com')
    const cell = name.closest('.name')
    expect(cell.firstChild).toHaveTextContent(/^host\.example\.com · Renamed$/)
    const plainCell = (await screen.findByText('plain.example.com')).closest('.name')
    expect(within(plainCell).getAllByText('plain.example.com')).toHaveLength(1)
  })

  it('the picker dialog counts the SANs of a certificate that has several', async () => {
    getAll.mockResolvedValue({ data: [{ ...renamed, san_count: 2 }, { ...plain, san_count: 1 }], meta: { total: 2 } })
    render(<CertificatePickerModal isOpen onClose={vi.fn()} onSelect={vi.fn()} />)
    expect(await screen.findByText(/2 details\.sans/)).toBeInTheDocument()
    const plainCell = (await screen.findByText('plain.example.com')).closest('.name')
    expect(plainCell).not.toHaveTextContent('details.sans')
  })
})
