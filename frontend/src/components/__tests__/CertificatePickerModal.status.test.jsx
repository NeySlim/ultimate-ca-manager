/**
 * The HTTPS certificate picker offers certificates in their last 30 days
 * (#378): a 27-day certificate is "expiring" from the day it is issued.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
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

  it('is the mockup dialog: a search, then one result per certificate, picked by a click', async () => {
    getAll.mockResolvedValue({ data: [cert(1, 'valid'), cert(2, 'expiring')], meta: { total: 2 } })
    const onSelect = vi.fn()
    const onClose = vi.fn()
    render(<CertificatePickerModal isOpen onClose={onClose} onSelect={onSelect} />)
    const dialog = screen.getByRole('dialog')
    expect(dialog.closest('.atl')).not.toBeNull()
    expect(dialog.querySelector('.command-search input')).toHaveAccessibleName('settings.certPickerSearch')
    fireEvent.click((await screen.findByText('expiring.example.com')).closest('button.command-result'))
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: 2 }))
    expect(onClose).toHaveBeenCalled()
  })

  it('sends what is typed as the search, from the first page', async () => {
    getAll.mockResolvedValue({ data: [cert(1, 'valid')], meta: { total: 1 } })
    render(<CertificatePickerModal isOpen onClose={vi.fn()} onSelect={vi.fn()} />)
    await screen.findByText('valid.example.com')
    fireEvent.change(screen.getByRole('searchbox', { name: 'settings.certPickerSearch' }), { target: { value: 'web' } })
    await waitFor(() => expect(getAll).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'web', page: 1 })))
  })

  it('says when no certificate qualifies', async () => {
    getAll.mockResolvedValue({ data: [], meta: { total: 0 } })
    render(<CertificatePickerModal isOpen onClose={vi.fn()} onSelect={vi.fn()} />)
    expect(await screen.findByText('settings.noValidCertificates')).toBeInTheDocument()
  })

  it('defaults to valid certificates only', async () => {
    getAll.mockResolvedValue({ data: [], meta: { total: 0 } })
    render(<CertificatePickerModal isOpen onClose={vi.fn()} onSelect={vi.fn()} />)
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    expect(getAll.mock.calls[0][0].status).toEqual(['valid'])
  })
})
