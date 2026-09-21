/**
 * ResponsiveDataTable — a disabled row action is inert, not just grey.
 *
 * `disabled` was added to rowActions so the Templates page could show Edit
 * and Delete on a system template without letting them be clicked: the
 * server answers 403 to both, and hiding the buttons outright reads as a
 * rendering glitch rather than an answer.
 *
 * Two separate things make that work — the `disabled` attribute, which
 * stops the click, and the faded styling, which shows why. A refactor that
 * keeps the styling and drops the attribute leaves a button that looks dead
 * and fires anyway. Every table in the application renders through this
 * component, so that failure would not stay on one page.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

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
const DATA = [{ id: 1, name: 'locked-row' }, { id: 2, name: 'open-row' }]

const onBlocked = vi.fn()
const onAllowed = vi.fn()

const renderTable = () => render(
  <ResponsiveDataTable
    data={DATA}
    columns={COLUMNS}
    rowActions={(row) => [
      {
        label: 'blocked-action',
        disabled: row.name === 'locked-row',
        disabledReason: 'not allowed here',
        onClick: onBlocked,
      },
      { label: 'allowed-action', onClick: onAllowed },
    ]}
  />
)

const buttonIn = (rowName, title) => {
  const row = screen.getByText(rowName).closest('tr')
  return row.querySelector(`button[title="${title}"]`)
}

describe('ResponsiveDataTable — disabled row actions', () => {
  beforeEach(() => {
    onBlocked.mockReset()
    onAllowed.mockReset()
  })

  it('does not run the handler when the action is disabled', () => {
    renderTable()
    const button = buttonIn('locked-row', 'not allowed here')
    fireEvent.click(button)
    expect(onBlocked).not.toHaveBeenCalled()
  })

  it('marks the button disabled rather than only styling it', () => {
    // Styling alone would leave a button that looks dead and fires anyway.
    renderTable()
    expect(buttonIn('locked-row', 'not allowed here').disabled).toBe(true)
  })

  it('shows the reason in place of the label when disabled', () => {
    renderTable()
    const row = screen.getByText('locked-row').closest('tr')
    const blocked = row.querySelector('button[title="not allowed here"]')
    // Hovering a dead button should say why, not repeat its name.
    expect(blocked.getAttribute('title')).toBe('not allowed here')
    expect(row.querySelector('button[title="blocked-action"]')).toBeNull()
  })

  it('leaves every other action on the same row working', () => {
    renderTable()
    fireEvent.click(buttonIn('locked-row', 'allowed-action'))
    expect(onAllowed).toHaveBeenCalledTimes(1)
  })

  it('leaves the same action working on a row that is not disabled', () => {
    // disabled is per row, not per action: the rowActions callback decides
    // each time, so a flag on one row must not leak to the next.
    renderTable()
    const button = buttonIn('open-row', 'blocked-action')
    expect(button.disabled).toBe(false)
    fireEvent.click(button)
    expect(onBlocked).toHaveBeenCalledTimes(1)
  })
})
