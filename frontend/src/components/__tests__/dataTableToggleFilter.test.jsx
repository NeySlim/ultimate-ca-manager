/**
 * ResponsiveDataTable: a toggle filter is a view switch, not a filter value.
 *
 * `type: 'toggle'` was added for the Templates page's Show system switch. The
 * filter-clearing and preset-saving paths predate it and treat every entry in
 * `toolbarFilters` as a value to blank or record, so a toggle was swept up by
 * both: Clear filters called onChange('') on it, which switches it off and
 * persists the empty string, and every saved preset carried showSystem: true
 * and re-applied it later.
 *
 * Every table in the application shares these paths, so any page that adds a
 * toggle inherits the same behaviour.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (opts && typeof opts.count === 'number' ? `${key}:${opts.count}` : key),
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

vi.mock('../../contexts', () => ({
  useMobile: () => ({ isMobile: false, isTablet: false }),
}))

import { ResponsiveDataTable } from '../ui/responsive/ResponsiveDataTable'

const COLUMNS = [{ key: 'name', header: 'Name', render: (v) => <span>{v}</span> }]
const PRESETS_KEY = 'test-table-presets'

const onToggle = vi.fn()
const onSource = vi.fn()
const onStatus = vi.fn()

const filters = ({ source = ['custom'], status = '' } = {}) => [
  {
    key: 'showSystem',
    type: 'toggle',
    label: 'Show system',
    value: true,
    onChange: onToggle,
  },
  {
    key: 'source',
    type: 'multiSelect',
    label: 'Source',
    value: source,
    onChange: onSource,
    options: [{ value: 'custom', label: 'Custom' }, { value: 'system', label: 'System' }],
  },
  {
    key: 'status',
    label: 'Status',
    value: status,
    onChange: onStatus,
    options: [{ value: 'active', label: 'Active' }],
  },
]

const renderTable = (props = {}) => render(
  <ResponsiveDataTable data={[]} columns={COLUMNS} toolbarFilters={filters()} {...props} />
)

describe('ResponsiveDataTable: clearing filters leaves a toggle alone', () => {
  beforeEach(() => {
    window.localStorage.clear()
    onToggle.mockReset()
    onSource.mockReset()
    onStatus.mockReset()
  })

  it('does not switch the toggle off from the empty-state Clear filters', () => {
    // onChange('') would both switch it off and store an empty string, which
    // reads back as "on" on the next load.
    renderTable()
    fireEvent.click(screen.getByText('table.clearFilters'))
    expect(onToggle).not.toHaveBeenCalled()
    expect(onSource).toHaveBeenCalledWith([])
  })

  it('does not switch the toggle off from the chip row Clear filters', () => {
    // Two chips are needed before the chip row offers Clear filters at all.
    renderTable({ data: [{ id: 1, name: 'row' }], toolbarFilters: filters({ status: 'active' }) })
    fireEvent.click(screen.getByText('table.clearFilters'))
    expect(onToggle).not.toHaveBeenCalled()
    expect(onSource).toHaveBeenCalledWith([])
    expect(onStatus).toHaveBeenCalledWith('')
  })

  it('does not count a toggle as an active filter', () => {
    // A switch that is simply on is not a filter the user has to clear, so
    // the empty state must not offer to clear it.
    render(
      <ResponsiveDataTable
        data={[]}
        columns={COLUMNS}
        emptyTitle="nothing here"
        toolbarFilters={[filters()[0]]}
      />
    )
    expect(screen.queryByText('table.clearFilters')).toBeNull()
    expect(screen.getByText('nothing here')).toBeTruthy()
  })

  it('keeps the toggle out of a saved preset', async () => {
    renderTable({ data: [{ id: 1, name: 'row' }], filterPresetsKey: PRESETS_KEY })

    fireEvent.click(screen.getByTitle('table.filterPresets'))
    fireEvent.click(screen.getByText('table.saveFilters'))
    fireEvent.change(screen.getByPlaceholderText('table.presetName'), { target: { value: 'Mine' } })
    fireEvent.click(screen.getByText('common.save'))

    await waitFor(() => expect(window.localStorage.getItem(PRESETS_KEY)).toBeTruthy())
    const saved = JSON.parse(window.localStorage.getItem(PRESETS_KEY))
    expect(saved[0].filters).toEqual({ source: ['custom'] })
    expect(saved[0].filters.showSystem).toBeUndefined()
  })
})
