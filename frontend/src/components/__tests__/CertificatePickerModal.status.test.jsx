/**
 * The HTTPS certificate picker offers certificates in their last 30 days
 * (#378): a 27-day certificate is "expiring" from the day it is issued.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
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

import CertificatePickerModal from '../CertificatePickerModal'

const future = '2099-01-01T00:00:00Z'
const cert = (id, status, extra = {}) => ({
  id, common_name: `${status}.example.com`, descr: '', has_private_key: true, valid_to: future, status, ...extra,
})

describe('CertificatePickerModal status filter', () => {
  beforeEach(() => getAll.mockReset())

  it('asks the server for the statuses and the private key it needs', async () => {
    getAll.mockResolvedValue({ data: [cert(1, 'valid'), cert(2, 'expiring')], meta: { total: 2 } })
    render(<CertificatePickerModal isOpen onClose={vi.fn()} onSelect={vi.fn()}
      filters={{ status: ['valid', 'expiring'], has_private_key: true }} />)
    expect(await screen.findByText('expiring.example.com')).toBeInTheDocument()
    expect(screen.getByText('valid.example.com')).toBeInTheDocument()
    expect(getAll.mock.calls[0][0]).toMatchObject({ status: ['valid', 'expiring'], has_private_key: true })
  })

  it('pages over the server total rather than the rows received', async () => {
    getAll.mockResolvedValue({ data: [cert(1, 'valid')], meta: { total: 45 } })
    render(<CertificatePickerModal isOpen onClose={vi.fn()} onSelect={vi.fn()}
      filters={{ has_private_key: true }} />)
    expect(await screen.findByText('1 / 3')).toBeInTheDocument()
  })

  it('a fresh array with the same statuses does not reload the list', async () => {
    getAll.mockResolvedValue({ data: [cert(1, 'valid')], meta: { total: 1 } })
    const props = { isOpen: true, onClose: vi.fn(), onSelect: vi.fn() }
    const { rerender } = render(<CertificatePickerModal {...props} filters={{ status: ['valid', 'expiring'] }} />)
    await screen.findByText('valid.example.com')
    rerender(<CertificatePickerModal {...props} filters={{ status: ['valid', 'expiring'] }} />)
    await waitFor(() => expect(getAll).toHaveBeenCalledTimes(1))
  })

  it('defaults to valid certificates only', async () => {
    getAll.mockResolvedValue({ data: [], meta: { total: 0 } })
    render(<CertificatePickerModal isOpen onClose={vi.fn()} onSelect={vi.fn()} />)
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    expect(getAll.mock.calls[0][0].status).toEqual(['valid'])
  })
})
