import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { Button } from '../Button'

describe('Button Component', () => {
  it('renders with correct text', () => {
    render(<Button>Click me</Button>)
    expect(screen.getByText('Click me')).toBeInTheDocument()
  })

  it('calls onClick when clicked', () => {
    const handleClick = vi.fn()
    render(<Button onClick={handleClick}>Click</Button>)
    
    fireEvent.click(screen.getByRole('button'))
    
    expect(handleClick).toHaveBeenCalledTimes(1)
  })

  it('is disabled when disabled prop is true', () => {
    render(<Button disabled>Click</Button>)
    expect(screen.getByRole('button')).toBeDisabled()
  })

  it('does not call onClick when disabled', () => {
    const handleClick = vi.fn()
    render(<Button onClick={handleClick} disabled>Click</Button>)
    
    fireEvent.click(screen.getByRole('button'))
    
    expect(handleClick).not.toHaveBeenCalled()
  })

  it('renders with primary variant by default (has gradient style)', () => {
    render(<Button>Primary</Button>)
    const button = screen.getByRole('button')
    expect(button.style.background).toContain('var(--gradient-accent)')
  })

  it('renders secondary variant correctly', () => {
    render(<Button variant="secondary">Secondary</Button>)
    const button = screen.getByRole('button')
    expect(button.className).toContain('bg-gradient-to-r')
    expect(button.className).toContain('border')
  })

  it('renders danger variant correctly (has gradient style)', () => {
    render(<Button variant="danger">Danger</Button>)
    const button = screen.getByRole('button')
    expect(button.style.background).toContain('linear-gradient')
  })

  it('renders ghost variant correctly', () => {
    render(<Button variant="ghost">Ghost</Button>)
    const button = screen.getByRole('button')
    expect(button.className).toContain('hover:bg-bg-tertiary')
  })

  it('renders small size correctly', () => {
    render(<Button size="sm">Small</Button>)
    const button = screen.getByRole('button')
    expect(button.className).toContain('px-2')
    expect(button.className).toContain('py-0.5')
    expect(button.className).toContain('text-xs')
  })

  it('renders large size correctly', () => {
    render(<Button size="lg">Large</Button>)
    const button = screen.getByRole('button')
    expect(button.className).toContain('px-4')
    expect(button.className).toContain('py-2')
  })

  it('renders children including icons', () => {
    render(
      <Button>
        <span data-testid="icon">🔒</span>
        Save
      </Button>
    )
    expect(screen.getByTestId('icon')).toBeInTheDocument()
    expect(screen.getByText('Save')).toBeInTheDocument()
  })

  it('applies custom className', () => {
    render(<Button className="custom-class">Custom</Button>)
    expect(screen.getByRole('button').className).toContain('custom-class')
  })
})
