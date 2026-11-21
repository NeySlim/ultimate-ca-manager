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
vi.mock('../../components/ui/responsive', () => ({
  ResponsiveLayout: ({ children }) => <div>{children}</div>,
  ResponsiveDataTable: ({ data = [], multiSelect, selectedIds, onSelectionChange, bulkActions, toolbarFilters = [] }) => (
    <div>
      <button onClick={() => toolbarFilters[0].onChange(['custom'])}>only-custom</button>
      {multiSelect && data.map((row) => (
        <input
          key={row.id} type="checkbox" aria-label={`select-${row.id}`}
          checked={selectedIds?.has(row.id) || false}
          onChange={() => {
            const next = new Set(selectedIds)
            if (next.has(row.id)) next.delete(row.id); else next.add(row.id)
            onSelectionChange(next)
          }}
        />
      ))}
      {multiSelect && selectedIds?.size > 0 && bulkActions}
    </div>
  ),
}))
vi.mock('../../components/SmartImport', () => ({ SmartImportModal: () => null }))

import TrustStorePage from '../TrustStorePage'

const renderPage = () => render(<MemoryRouter><TrustStorePage /></MemoryRouter>)

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
    fireEvent.click(await screen.findByLabelText('select-1'))
    fireEvent.click(screen.getByLabelText('select-2'))
    fireEvent.click(screen.getByText('trustStore.deleteSelected'))
    await waitFor(() => expect(bulkDelete).toHaveBeenCalledWith([1, 2]))
    expect(confirm).toHaveBeenCalledWith('trustStore.confirmBulkRemove:2', expect.anything())
    await waitFor(() => expect(showSuccess).toHaveBeenCalledWith('trustStore.bulkRemoved:2'))
    await waitFor(() => expect(getAll).toHaveBeenCalledTimes(2))
  })

  it('reports the rows the server could not remove', async () => {
    bulkDelete.mockResolvedValue({ data: { success: [1], failed: [{ id: 2, error: 'Not found' }] } })
    renderPage()
    fireEvent.click(await screen.findByLabelText('select-1'))
    fireEvent.click(screen.getByLabelText('select-2'))
    fireEvent.click(screen.getByText('trustStore.deleteSelected'))
    await waitFor(() => expect(showError).toHaveBeenCalledWith('trustStore.bulkRemoveFailed:1'))
  })

  it('never removes a selected row the filters now hide', async () => {
    renderPage()
    fireEvent.click(await screen.findByLabelText('select-1'))
    fireEvent.click(screen.getByLabelText('select-3'))
    fireEvent.click(screen.getByText('only-custom'))
    fireEvent.click(screen.getByText('trustStore.deleteSelected'))
    await waitFor(() => expect(bulkDelete).toHaveBeenCalledWith([3]))
  })

  it('does nothing when the confirmation is declined', async () => {
    confirm.mockResolvedValue(false)
    renderPage()
    fireEvent.click(await screen.findByLabelText('select-1'))
    fireEvent.click(screen.getByText('trustStore.deleteSelected'))
    await waitFor(() => expect(confirm).toHaveBeenCalled())
    expect(bulkDelete).not.toHaveBeenCalled()
  })

  it('offers no selection without the delete permission', async () => {
    mockCanDelete = false
    renderPage()
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    expect(screen.queryByLabelText('select-1')).toBeNull()
  })
})
