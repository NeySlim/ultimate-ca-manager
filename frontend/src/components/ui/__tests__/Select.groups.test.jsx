/**
 * Options sharing a `group` string render under a heading in the open list.
 * jsdom needs the same Radix polyfills as the empty-option test.
 */
import { describe, it, expect, vi, beforeAll } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Select } from '../Select'

beforeAll(() => {
  // The global setup mocks ResizeObserver with a non-constructible arrow
  // function; @floating-ui (Radix popper) does `new ResizeObserver(...)`.
  global.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture || (() => false)
  Element.prototype.setPointerCapture = Element.prototype.setPointerCapture || (() => {})
  Element.prototype.releasePointerCapture = Element.prototype.releasePointerCapture || (() => {})
  Element.prototype.scrollIntoView = Element.prototype.scrollIntoView || (() => {})
})

const GROUPED = [
  { value: 'a', label: 'Alpha', group: 'First' },
  { value: 'b', label: 'Beta', group: 'First' },
  { value: 'c', label: 'Gamma', group: 'Second' },
]

describe('Select option groups', () => {
  it('renders one heading per run of options and keeps them selectable', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<Select options={GROUPED} value="a" onChange={onChange} />)
    await user.click(screen.getByRole('combobox'))
    expect(await screen.findByText('First')).toBeInTheDocument()
    expect(screen.getByText('Second')).toBeInTheDocument()
    expect(screen.getAllByRole('group')).toHaveLength(2)
    await user.click(screen.getByRole('option', { name: 'Gamma' }))
    expect(onChange).toHaveBeenCalledWith('c')
  })

  it('renders no heading when no option carries a group', async () => {
    const user = userEvent.setup()
    render(<Select options={[{ value: 'a', label: 'Alpha' }]} value="a" onChange={() => {}} />)
    await user.click(screen.getByRole('combobox'))
    await screen.findByRole('option', { name: 'Alpha' })
    expect(screen.queryAllByRole('group')).toHaveLength(0)
  })
})
