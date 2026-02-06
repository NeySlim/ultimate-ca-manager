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
})
