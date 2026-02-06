import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { Pagination } from '../Pagination'

describe('Pagination Component', () => {
  const defaultProps = {
    total: 100,
    page: 1,
    perPage: 20,
    onChange: vi.fn(),
  }

  it('renders pagination info', () => {
    render(<Pagination {...defaultProps} />)
    // Multiple "1" elements (page 1 button + start of range)
    expect(screen.getAllByText('1').length).toBeGreaterThan(0)
    expect(screen.getByText('20')).toBeInTheDocument()
    expect(screen.getByText('100')).toBeInTheDocument()
  })

  it('calculates correct total pages', () => {
    render(<Pagination {...defaultProps} />)
    // With 100 items and 20 per page = 5 pages
    expect(screen.getByText('5')).toBeInTheDocument()
  })

  it('handles page change', () => {
    const onChange = vi.fn()
    render(<Pagination {...defaultProps} onChange={onChange} />)
    
    fireEvent.click(screen.getByText('2'))
    expect(onChange).toHaveBeenCalledWith(2)
  })

  it('disables previous buttons on first page', () => {
    render(<Pagination {...defaultProps} page={1} />)
    const buttons = screen.getAllByRole('button')
    // First two buttons should be disabled (double left, left)
    expect(buttons[0]).toBeDisabled()
    expect(buttons[1]).toBeDisabled()
  })

  it('disables next buttons on last page', () => {
    render(<Pagination {...defaultProps} page={5} />)
    const buttons = screen.getAllByRole('button')
    const lastIdx = buttons.length - 1
    expect(buttons[lastIdx]).toBeDisabled()
    expect(buttons[lastIdx - 1]).toBeDisabled()
  })

  it('highlights current page', () => {
    render(<Pagination {...defaultProps} page={3} />)
    const currentPage = screen.getByText('3')
    expect(currentPage.className).toContain('bg-accent-primary')
  })

  it('shows per page selector when onPerPageChange provided', () => {
    const onPerPageChange = vi.fn()
    render(<Pagination {...defaultProps} onPerPageChange={onPerPageChange} />)
    
    // Radix Select uses a trigger button with combobox role
    const trigger = screen.getByRole('combobox')
    expect(trigger).toBeInTheDocument()
  })

  // Note: Testing Radix Select interaction in jsdom is problematic
  // because jsdom lacks pointer capture support. This is tested via E2E.
  it('per page selector displays current value', () => {
    const onPerPageChange = vi.fn()
    render(<Pagination {...defaultProps} perPage={50} onPerPageChange={onPerPageChange} />)
    
    const trigger = screen.getByRole('combobox')
    expect(trigger.textContent).toContain('50')
  })

  it('hides info when showInfo is false', () => {
    render(<Pagination {...defaultProps} showInfo={false} />)
    expect(screen.queryByText('of')).not.toBeInTheDocument()
  })

  it('hides per page selector when showPerPageSelector is false', () => {
    render(<Pagination {...defaultProps} showPerPageSelector={false} onPerPageChange={vi.fn()} />)
    expect(screen.queryByText('Rows:')).not.toBeInTheDocument()
  })

  it('navigates to first page with double left button', () => {
    const onChange = vi.fn()
    render(<Pagination {...defaultProps} page={3} onChange={onChange} />)
    const buttons = screen.getAllByRole('button')
    fireEvent.click(buttons[0]) // First button = go to first
    expect(onChange).toHaveBeenCalledWith(1)
  })

  it('navigates to previous page with left button', () => {
    const onChange = vi.fn()
    render(<Pagination {...defaultProps} page={3} onChange={onChange} />)
    const buttons = screen.getAllByRole('button')
    fireEvent.click(buttons[1]) // Second button = previous
    expect(onChange).toHaveBeenCalledWith(2)
  })

  it('navigates to next page with right button', () => {
    const onChange = vi.fn()
    render(<Pagination {...defaultProps} page={3} onChange={onChange} />)
    const buttons = screen.getAllByRole('button')
    const lastIdx = buttons.length - 1
    fireEvent.click(buttons[lastIdx - 1]) // Second to last = next
    expect(onChange).toHaveBeenCalledWith(4)
  })

  it('navigates to last page with double right button', () => {
    const onChange = vi.fn()
    render(<Pagination {...defaultProps} page={3} onChange={onChange} />)
    const buttons = screen.getAllByRole('button')
    const lastIdx = buttons.length - 1
    fireEvent.click(buttons[lastIdx]) // Last button = go to last
    expect(onChange).toHaveBeenCalledWith(5)
  })

  it('shows correct range for middle pages (totalPages > 5)', () => {
    render(<Pagination total={200} page={6} perPage={20} onChange={vi.fn()} />)
    // 200/20 = 10 pages, page 6 should show 4,5,6,7,8
    expect(screen.getByText('4')).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()
    expect(screen.getByText('6')).toBeInTheDocument()
    expect(screen.getByText('7')).toBeInTheDocument()
    expect(screen.getByText('8')).toBeInTheDocument()
  })

  it('shows correct range near end (page >= totalPages - 2)', () => {
    render(<Pagination total={200} page={9} perPage={20} onChange={vi.fn()} />)
    // 10 pages, near end should show 6,7,8,9,10
    expect(screen.getByText('6')).toBeInTheDocument()
    expect(screen.getByText('7')).toBeInTheDocument()
    expect(screen.getByText('8')).toBeInTheDocument()
    expect(screen.getByText('9')).toBeInTheDocument()
    expect(screen.getByText('10')).toBeInTheDocument()
  })

  it('handles zero total items', () => {
    const { container } = render(<Pagination total={0} page={1} perPage={20} onChange={vi.fn()} />)
    // When total is 0, component should render without crashing
    expect(container.firstChild).toBeInTheDocument()
  })

  it('handles default props', () => {
    render(<Pagination onChange={vi.fn()} />)
    // Should not crash with minimal props
    expect(screen.getAllByRole('button').length).toBeGreaterThan(0)
  })
})
