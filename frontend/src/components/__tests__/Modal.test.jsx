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

  // Widths of the mockup's dialog: narrow 520 (sm), default 760 (md), wide 920 (lg, xl)
  it('takes the mockup width for each size', () => {
    const { rerender } = render(<Modal {...defaultProps} size="sm" />)
    expect(screen.getByRole('dialog').className).toMatch(/\blv-dialog\b.*\bis-narrow\b/)
    rerender(<Modal {...defaultProps} size="md" />)
    expect(screen.getByRole('dialog').className).not.toMatch(/is-narrow|is-wide/)
    for (const size of ['lg', 'xl']) {
      rerender(<Modal {...defaultProps} size={size} />)
      expect(screen.getByRole('dialog').className).toContain('is-wide')
    }
  })

  it('names its close button and its title', () => {
    render(<Modal {...defaultProps} />)
    expect(screen.getByRole('dialog', { name: 'Test Modal' })).toBeInTheDocument()
    expect(screen.getByRole('button').getAttribute('aria-label')).toBeTruthy()
  })

  it('hides close button when showClose is false', () => {
    render(<Modal {...defaultProps} showClose={false} />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
