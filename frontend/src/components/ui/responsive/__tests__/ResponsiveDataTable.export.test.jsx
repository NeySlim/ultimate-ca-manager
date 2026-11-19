/**
 * ResponsiveDataTable export: a table paged by the server exports the whole
 * filtered list through its loader, never just the page on screen.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (opts ? `${key}:${JSON.stringify(opts)}` : key),
    i18n: { language: 'en', changeLanguage: () => {} },
  }),
}))
vi.mock('../../../../contexts', () => ({
  useMobile: () => ({ isMobile: false, isTablet: false, isDesktop: true }),
}))

const exported = vi.hoisted(() => ({ csv: vi.fn(), json: vi.fn() }))
vi.mock('../../../../lib/utils', async () => {
  const actual = await vi.importActual('../../../../lib/utils')
  return { ...actual, exportToCSV: exported.csv, exportToJSON: exported.json }
})

import { ResponsiveDataTable } from '../ResponsiveDataTable'

const columns = [{ key: 'name', header: 'Name' }]
const pageRows = [{ id: 1, name: 'a' }, { id: 2, name: 'b' }]
const range = (from, to) => Array.from({ length: to - from + 1 }, (_, i) => ({ id: from + i, name: `r${from + i}` }))

const open = async () => {
  fireEvent.click(await screen.findByTitle('table.exportData'))
  return screen.findByText('table.exportCSV')
}

describe('ResponsiveDataTable export', () => {
  beforeEach(() => { exported.csv.mockReset(); exported.json.mockReset() })

  it('walks every page of a server-paged table', async () => {
    const exportLoader = vi.fn(async ({ page, per_page }) => ({
      data: range((page - 1) * per_page + 1, Math.min(page * per_page, 250)), meta: { total: 250 },
    }))
    render(
      <ResponsiveDataTable
        data={pageRows} columns={columns} searchable exportEnabled exportFilename="x"
        exportLoader={exportLoader}
        pagination={{ page: 1, total: 250, perPage: 2, onChange: vi.fn(), onPerPageChange: vi.fn() }}
      />,
    )
    fireEvent.click(await open())
    await waitFor(() => expect(exported.csv).toHaveBeenCalled())
    expect(exported.csv.mock.calls[0][0]).toHaveLength(250)
    expect(exportLoader).toHaveBeenCalledTimes(3)
  })

  it('says when the export is cut at the ceiling', async () => {
    const exportLoader = async ({ page, per_page }) => ({
      data: range((page - 1) * per_page + 1, page * per_page), meta: { total: 12345 },
    })
    render(
      <ResponsiveDataTable
        data={pageRows} columns={columns} searchable exportEnabled exportLoader={exportLoader}
        pagination={{ page: 1, total: 12345, perPage: 2, onChange: vi.fn(), onPerPageChange: vi.fn() }}
      />,
    )
    fireEvent.click(await open())
    await waitFor(() => expect(exported.csv).toHaveBeenCalled())
    expect(exported.csv.mock.calls[0][0]).toHaveLength(10000)
    expect(await screen.findByRole('status')).toHaveTextContent('table.exportTruncated')
    expect(screen.getByRole('status')).toHaveTextContent('12345')
  })

  it('exports the rows of a table not paged by the server as they are', async () => {
    render(<ResponsiveDataTable data={pageRows} columns={columns} searchable exportEnabled />)
    fireEvent.click(await open())
    expect(exported.csv.mock.calls[0][0]).toEqual(pageRows)
  })

  it('offers no export of a server-paged table that cannot load the rest', async () => {
    render(
      <ResponsiveDataTable
        data={pageRows} columns={columns} searchable exportEnabled
        pagination={{ page: 1, total: 250, perPage: 2, onChange: vi.fn(), onPerPageChange: vi.fn() }}
      />,
    )
    await screen.findByText('a')
    expect(screen.queryByTitle('table.exportData')).not.toBeInTheDocument()
  })
})
