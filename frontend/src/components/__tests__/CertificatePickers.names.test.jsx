/**
 * The certificate pickers name a certificate the way the list does: its CN, with
 * the description (Rename) alongside when it says something else (#365).
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

vi.mock('../ui/Select', () => ({
  Select: ({ options = [] }) => (
    <select>{options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select>
  ),
}))

vi.mock('../Modal', () => ({
  Modal: ({ open, children }) => (open ? <div>{children}</div> : null),
}))

vi.mock('../index.js', () => ({
  Modal: ({ open, children }) => (open ? <div>{children}</div> : null),
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Input: (props) => <input {...props} />,
  Badge: ({ children }) => <span>{children}</span>,
  EmptyState: ({ title }) => <div>{title}</div>,
  LoadingSpinner: () => <div>loading</div>,
}))

const getAll = vi.fn()
vi.mock('../../services', () => ({
  certificatesService: { getAll: (...a) => getAll(...a) },
}))

import { CertificateCompareModal } from '../CertificateCompareModal'
import CertificatePickerModal from '../CertificatePickerModal'

const renamed = { id: 7, common_name: 'host.example.com', descr: 'Renamed', key_type: 'EC', has_private_key: true, valid_to: '2099-01-01T00:00:00Z' }
const plain = { id: 8, common_name: 'plain.example.com', descr: 'plain.example.com', has_private_key: true, valid_to: '2099-01-01T00:00:00Z' }

const optionLabels = () => Array.from(document.querySelectorAll('option')).map((o) => o.textContent)

describe('certificate pickers name a certificate by its CN (#365)', () => {
  it('the compare dialog lists the CN with the description alongside', () => {
    render(<CertificateCompareModal open onClose={vi.fn()} certificates={[renamed, plain]} />)
    expect(optionLabels()).toContain('host.example.com · Renamed (EC)')
    expect(optionLabels()).toContain('plain.example.com')
  })

  it('the picker dialog shows the CN with the description under it', async () => {
    getAll.mockResolvedValue({ data: [renamed, plain], meta: { total: 2 } })
    render(<CertificatePickerModal isOpen onClose={vi.fn()} onSelect={vi.fn()} />)
    const name = await screen.findByText('host.example.com')
    const cell = name.closest('td')
    expect(cell).toHaveTextContent(/^host\.example\.comRenamed$/)
    const plainCell = (await screen.findByText('plain.example.com')).closest('td')
    expect(within(plainCell).getAllByText('plain.example.com')).toHaveLength(1)
  })

  it('the picker dialog counts the SANs of a certificate that has several', async () => {
    getAll.mockResolvedValue({ data: [{ ...renamed, san_count: 2 }, { ...plain, san_count: 1 }], meta: { total: 2 } })
    render(<CertificatePickerModal isOpen onClose={vi.fn()} onSelect={vi.fn()} />)
    expect(await screen.findByText('2 details.sans')).toBeInTheDocument()
    const plainCell = (await screen.findByText('plain.example.com')).closest('td')
    expect(plainCell).not.toHaveTextContent('details.sans')
  })
})
