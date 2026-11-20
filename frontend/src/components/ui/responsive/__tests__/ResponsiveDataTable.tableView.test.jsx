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
