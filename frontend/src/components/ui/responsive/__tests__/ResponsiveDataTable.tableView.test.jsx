/**
 * The table outside the list template is the mockup's table view: `ui-table`, rows at the
 * density height, the opened row marked apart from the ticked ones.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key, i18n: { language: 'en', changeLanguage: () => {} } }),
}))
vi.mock('../../../../contexts', () => ({
  useMobile: () => ({ isMobile: false, isTablet: false, isDesktop: true }),
}))

import { ResponsiveDataTable } from '../ResponsiveDataTable'

const columns = [{ key: 'name', header: 'Name' }]
const rows = [{ id: 1, name: 'alpha' }, { id: 2, name: 'beta' }, { id: 3, name: 'gamma' }]

describe('ResponsiveDataTable table view', () => {
  it('draws the mockup table at the 36 px row of the compact density', () => {
    render(<ResponsiveDataTable data={rows} columns={columns} />)
    const table = screen.getByRole('table')
    expect(table.className).toContain('ui-table')
    expect(table.style.getPropertyValue('--ui-row')).toBe('36px')
    expect(table.querySelector('thead').className).not.toMatch(/gradient|shadow/)
  })

  it('marks the opened row apart from the ticked ones', () => {
    const onSelectionChange = vi.fn()
    const { rerender } = render(
      <ResponsiveDataTable data={rows} columns={columns} selectedId={1} />
    )
    expect(screen.getByText('alpha').closest('tr').className).toContain('is-opened')
    expect(screen.getByText('beta').closest('tr').className).not.toContain('is-opened')

    rerender(
      <ResponsiveDataTable data={rows} columns={columns} multiSelect selectedIds={new Set([2])} onSelectionChange={onSelectionChange} />
    )
    const beta = screen.getByText('beta').closest('tr')
    expect(beta.className).toContain('is-checked')
    expect(beta.className).not.toContain('is-opened')
    fireEvent.click(screen.getByText('gamma'))
    expect(onSelectionChange).toHaveBeenCalled()
  })
})

describe('ResponsiveDataTable table view: column widths', () => {
  const wide = [
    { key: 'common_name', header: 'Name' },
    { key: 'status', header: 'Status' },
    { key: 'created_at', header: 'Created' },
    { key: 'description', header: 'Description', size: 2 },
    { key: 'logger', header: 'Component' },
    { key: 'mystery', header: 'Unknown' },
    { key: 'note_count', header: 'Forced', fit: false },
    { key: 'cn', header: 'Forced fit', fit: true },
    { key: 'type', header: 'Fixed', width: '80px' },
  ]
  const cells = (table) => [...table.querySelectorAll('thead th')].map((th) => [th.textContent, th.className.match(/\b(fit|share)\b/)?.[1] || '', th.style.width])

  it('sizes the short fixed-format columns to their content and shares the rest among the others by weight', () => {
    render(<ResponsiveDataTable data={[{ id: 1, common_name: 'web', status: 'Valid', created_at: '2026-01-01', description: 'd', logger: 'api', mystery: 'x', note_count: 1, cn: 'c', type: 't' }]} columns={wide} />)
    const table = screen.getByRole('table')
    // weights 3, 2 (its size), 1.5 and 1 share the room the fitted columns leave;
    // the browser lays the table out from the contents, no longer from fixed shares
    expect(table.style.tableLayout).toBe('')
    expect(cells(table)).toEqual([
      ['Name', 'share', '40%'],
      ['Status', 'fit', ''],
      ['Created', 'fit', ''],
      ['Description', 'share', '26.67%'],
      ['Component', 'fit', ''],
      ['Unknown', 'share', '20%'],
      ['Forced', 'share', '13.33%'],
      ['Forced fit', 'fit', ''],
      ['Fixed', '', '80px'],
    ])
    // the body cells carry the class of their column
    const row = table.querySelector('tbody tr')
    expect([...row.children].map((td) => td.className.match(/\b(fit|share)\b/)?.[1] || '')).toEqual(['share', 'fit', 'fit', 'share', 'fit', 'share', 'share', 'fit', ''])
  })

  it('keeps a width set by hand in pixels', () => {
    localStorage.setItem('ucm-widths-test-widths', JSON.stringify({ status: 140 }))
    render(<ResponsiveDataTable data={[{ id: 1, common_name: 'web', status: 'Valid' }]} columns={wide.slice(0, 2)} columnStorageKey="ucm-widths-test" />)
    const status = screen.getByRole('columnheader', { name: 'Status' })
    expect(status.style.width).toBe('140px')
    expect(status.className).not.toMatch(/\b(fit|share)\b/)
    localStorage.removeItem('ucm-widths-test-widths')
  })
})

