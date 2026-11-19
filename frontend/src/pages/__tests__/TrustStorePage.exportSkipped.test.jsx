/**
 * TrustStorePage: a bundle export that left unreadable entries out says so.
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
const showWarning = vi.fn()
vi.mock('../../contexts', () => ({
  useNotification: () => ({
    showSuccess, showError, showInfo: vi.fn(), showWarning, showConfirm: confirm,
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
const exportBundle = vi.fn()
const getAll = vi.fn()
vi.mock('../../services', () => ({
  truststoreService: {
    getAll: (...a) => getAll(...a),
    getStats: vi.fn().mockResolvedValue({ data: { total: 3, root_ca: 0, intermediate_ca: 0, expired: 2, valid: 1 } }),
    bulkDelete: (...a) => bulkDelete(...a),
    exportBundle: (...a) => exportBundle(...a),
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
  ResponsiveDataTable: ({ data = [], multiSelect, selectedIds, onSelectionChange, bulkActions, toolbarFilters = [], toolbarActions }) => (
    <div>
      {toolbarActions}
      <button onClick={() => toolbarFilters[0].onChange(['custom'])}>only-custom</button>
      <button onClick={() => toolbarFilters[1].onChange(['expired'])}>only-expired</button>
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

const bundle = (skipped) => {
  const blob = new Blob(['pem'])
  if (skipped) blob.skippedCount = skipped
  return blob
}

describe('TrustStorePage bundle export', () => {
  beforeEach(() => {
    showSuccess.mockReset()
    showWarning.mockReset()
    showError.mockReset()
    getAll.mockReset().mockResolvedValue({ data: ROWS })
    URL.createObjectURL = vi.fn(() => 'blob:x')
    URL.revokeObjectURL = vi.fn()
  })

  it('warns that unreadable entries were not exported', async () => {
    exportBundle.mockReset().mockResolvedValue(bundle(2))
    renderPage()
    fireEvent.click(await screen.findByTitle('trustStore.exportBundle'))
    await waitFor(() => expect(showWarning).toHaveBeenCalledWith('export.skippedUnreadable:2'))
    expect(showSuccess).toHaveBeenCalledWith('trustStore.bundleExported')
  })

  it('says nothing more when every entry was exported', async () => {
    exportBundle.mockReset().mockResolvedValue(bundle(0))
    renderPage()
    fireEvent.click(await screen.findByTitle('trustStore.exportBundle'))
    await waitFor(() => expect(showSuccess).toHaveBeenCalledWith('trustStore.bundleExported'))
    expect(showWarning).not.toHaveBeenCalled()
  })

  it('exports the purposes the filter shows', async () => {
    exportBundle.mockReset().mockResolvedValue(bundle(0))
    renderPage()
    fireEvent.click(await screen.findByText('only-custom'))
    fireEvent.click(await screen.findByTitle('trustStore.exportBundle'))
    await waitFor(() => expect(exportBundle).toHaveBeenCalledWith('pem', ['custom'], []))
  })

  it('exports everything with no filter', async () => {
    exportBundle.mockReset().mockResolvedValue(bundle(0))
    renderPage()
    fireEvent.click(await screen.findByTitle('trustStore.exportBundle'))
    await waitFor(() => expect(exportBundle).toHaveBeenCalledWith('pem', 'all', []))
  })

  it('exports the expiry states the filter shows', async () => {
    exportBundle.mockReset().mockResolvedValue(bundle(0))
    renderPage()
    fireEvent.click(await screen.findByText('only-expired'))
    fireEvent.click(await screen.findByTitle('trustStore.exportBundle'))
    await waitFor(() => expect(exportBundle).toHaveBeenCalledWith('pem', 'all', ['expired']))
  })
})
