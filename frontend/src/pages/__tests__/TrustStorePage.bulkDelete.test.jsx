/**
 * TrustStorePage: a selection is removed in one go (#388), and only the rows
 * the current filters still show.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (opts && typeof opts.count === 'number' ? `${key}:${opts.count}` : key),
  }),
}))

const confirm = vi.fn()
const showSuccess = vi.fn()
const showError = vi.fn()
vi.mock('../../contexts', () => ({
  useNotification: () => ({
    showSuccess, showError, showInfo: vi.fn(), showWarning: vi.fn(), showConfirm: confirm,
  }),
  useMobile: () => ({ isMobile: false }),
  useInspector: () => ({ openEntity: vi.fn(), closeWindow: vi.fn(), windows: [] }),
}))
vi.mock('../../contexts/InspectorContext', () => ({
  useInspector: () => ({ openEntity: vi.fn(), closeWindow: vi.fn(), windows: [] }),
}))
vi.mock('../../contexts/MobileContext', () => ({ useMobile: () => ({ isMobile: false }) }))

let mockCanDelete = true
vi.mock('../../hooks', async () => {
  const modals = await vi.importActual('../../hooks/useCommon')
  const { useState } = await vi.importActual('react')
  return {
    useModals: modals.useModals,
    // Filters start empty in every test, whatever an earlier one chose
    usePersistedState: (_key, initial) => useState(initial),
    usePermission: () => ({
      canWrite: () => true, canDelete: () => mockCanDelete, hasPermission: () => true, canRead: () => true,
    }),
  }
})

const ROWS = [
  { id: 1, name: 'Old root', purpose: 'system', not_after: '2020-01-01T00:00:00Z' },
  { id: 2, name: 'Other root', purpose: 'system', not_after: '2020-01-01T00:00:00Z' },
  { id: 3, name: 'Mine', purpose: 'custom', not_after: '2099-01-01T00:00:00Z' },
]
const bulkDelete = vi.fn()
const getAll = vi.fn()
vi.mock('../../services', () => ({
  truststoreService: {
    getAll: (...a) => getAll(...a),
    getStats: vi.fn().mockResolvedValue({ data: { total: 3, root_ca: 0, intermediate_ca: 0, expired: 2, valid: 1 } }),
    bulkDelete: (...a) => bulkDelete(...a),
  },
  casService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
}))

vi.mock('../../components', () => ({
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Input: (props) => <input {...props} />,
  Badge: ({ children }) => <span>{children}</span>,
  Modal: ({ open, children }) => (open ? <div>{children}</div> : null),
  Textarea: (props) => <textarea {...props} />,
  HelpCard: ({ children }) => <div>{children}</div>,
  CompactSection: ({ children }) => <div>{children}</div>,
  CompactGrid: ({ children }) => <div>{children}</div>,
  CompactField: () => null,
  FormSelect: () => null,
}))
vi.mock('../../components/SmartImport', () => ({ SmartImportModal: () => null }))

import TrustStorePage from '../TrustStorePage'

const renderPage = () => render(<MemoryRouter><TrustStorePage /></MemoryRouter>)
// A row's checkbox, once the rows are drawn
const box = async (id) => { await screen.findByText('Old root'); return document.querySelector(`[data-select="${id}"]`) }

describe('TrustStorePage bulk removal (#388)', () => {
  beforeEach(() => {
    mockCanDelete = true
    confirm.mockReset().mockResolvedValue(true)
    showSuccess.mockReset()
    showError.mockReset()
    getAll.mockReset().mockResolvedValue({ data: ROWS })
    bulkDelete.mockReset().mockResolvedValue({ data: { success: [1, 2], failed: [] } })
  })

  it('removes the selected rows in one request', async () => {
    renderPage()
    fireEvent.click(await box(1))
    fireEvent.click(await box(2))
    fireEvent.click(screen.getByText('trustStore.deleteSelected'))
    await waitFor(() => expect(bulkDelete).toHaveBeenCalledWith([1, 2]))
    expect(confirm).toHaveBeenCalledWith('trustStore.confirmBulkRemove:2', expect.anything())
    await waitFor(() => expect(showSuccess).toHaveBeenCalledWith('trustStore.bulkRemoved:2'))
    await waitFor(() => expect(getAll).toHaveBeenCalledTimes(2))
  })

  it('reports the rows the server could not remove', async () => {
    bulkDelete.mockResolvedValue({ data: { success: [1], failed: [{ id: 2, error: 'Not found' }] } })
    renderPage()
    fireEvent.click(await box(1))
    fireEvent.click(await box(2))
    fireEvent.click(screen.getByText('trustStore.deleteSelected'))
    await waitFor(() => expect(showError).toHaveBeenCalledWith('trustStore.bulkRemoveFailed:1'))
  })

  it('never removes a selected row the filters now hide', async () => {
    renderPage()
    fireEvent.click(await box(1))
    fireEvent.click(await box(3))
    fireEvent.change(screen.getByRole('combobox', { name: 'trustStore.module.filterByType' }), { target: { value: 'custom' } })
    fireEvent.click(screen.getByText('trustStore.deleteSelected'))
    await waitFor(() => expect(bulkDelete).toHaveBeenCalledWith([3]))
  })

  it('does nothing when the confirmation is declined', async () => {
    confirm.mockResolvedValue(false)
    renderPage()
    fireEvent.click(await box(1))
    fireEvent.click(screen.getByText('trustStore.deleteSelected'))
    await waitFor(() => expect(confirm).toHaveBeenCalled())
    expect(bulkDelete).not.toHaveBeenCalled()
  })

  it('offers no selection without the delete permission', async () => {
    mockCanDelete = false
    renderPage()
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    await screen.findByText('Old root')
    expect(document.querySelector('[data-select]')).toBeNull()
  })

  it('pages a long store by 25, keeps the ticks of every page and removes them together', async () => {
    const many = Array.from({ length: 30 }, (_, i) => ({ id: 10 + i, name: `Anchor ${String(i + 1).padStart(2, '0')}`, purpose: 'system', not_after: `2030-01-${String(30 - i).padStart(2, '0')}T00:00:00Z` }))
    getAll.mockResolvedValue({ data: many })
    bulkDelete.mockResolvedValue({ data: { success: many.map((c) => c.id), failed: [] } })
    const { container } = renderPage()
    await screen.findByText('Anchor 01')
    const footer = container.querySelector('footer.table-footer')
    expect(container.querySelectorAll('tbody tr')).toHaveLength(25)
    expect(footer).toHaveTextContent('1 / 2')
    fireEvent.click(screen.getByRole('checkbox', { name: 'table.selectPage' }))
    fireEvent.click(screen.getByRole('button', { name: 'table.nextPage' }))
    expect(container.querySelectorAll('tbody tr')).toHaveLength(5)
    fireEvent.click(screen.getByRole('checkbox', { name: 'table.selectPage' }))
    expect(screen.getByText('trustStore.module.selected:30')).toBeInTheDocument()
    // The expiry sorts from its header, back to page one
    fireEvent.click(screen.getByRole('button', { name: 'trustStore.module.expires' }))
    expect(footer).toHaveTextContent('1 / 2')
    expect(container.querySelector('tbody tr')).toHaveTextContent('Anchor 30')
    for (const name of ['trustStore.module.subject', 'trustStore.module.usage', 'common.type', 'atelier.state']) {
      fireEvent.click(screen.getByRole('button', { name }))
      expect(screen.getByRole('columnheader', { name })).toHaveAttribute('aria-sort', 'ascending')
    }
    // Unticking the page leaves the ticks of the other page
    fireEvent.click(screen.getByRole('checkbox', { name: 'table.selectPage' }))
    expect(screen.getByText('trustStore.module.selected:5')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox', { name: 'table.selectPage' }))
    fireEvent.click(screen.getByText('trustStore.deleteSelected'))
    await waitFor(() => expect(bulkDelete).toHaveBeenCalledWith(expect.arrayContaining(many.map((c) => c.id))))
    expect(bulkDelete.mock.calls[0][0]).toHaveLength(30)
  })
})
