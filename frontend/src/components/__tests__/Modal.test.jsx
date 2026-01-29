import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { Modal } from '../Modal'

describe('Modal Component', () => {
  const defaultProps = {
    open: true,
    onClose: vi.fn(),
    title: 'Test Modal',
    children: <p>Modal content</p>,
  }

  it('renders when open', () => {
    render(<Modal {...defaultProps} />)
    expect(screen.getByText('Test Modal')).toBeInTheDocument()
    expect(screen.getByText('Modal content')).toBeInTheDocument()
  })

  it('does not render when closed', () => {
    render(<Modal {...defaultProps} open={false} />)
    expect(screen.queryByText('Test Modal')).not.toBeInTheDocument()
  })

  it('calls onClose when clicking close button', () => {
    const onClose = vi.fn()
    render(<Modal {...defaultProps} onClose={onClose} showClose={true} />)
    
    // Find close button (X icon)
    const closeButton = screen.getByRole('button')
    fireEvent.click(closeButton)
    expect(onClose).toHaveBeenCalled()
  })

  it('applies size class', () => {
    render(<Modal {...defaultProps} size="lg" />)
    expect(screen.getByRole('dialog').className).toContain('max-w-4xl')
  })

  it('renders different sizes', () => {
    const { rerender } = render(<Modal {...defaultProps} size="sm" />)
    expect(screen.getByRole('dialog').className).toContain('max-w-md')
    
    rerender(<Modal {...defaultProps} size="xl" />)
    expect(screen.getByRole('dialog').className).toContain('max-w-6xl')
  })

  it('hides close button when showClose is false', () => {
    render(<Modal {...defaultProps} showClose={false} />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
