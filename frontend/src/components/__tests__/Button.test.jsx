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
    render(<Button type="button" onClick={handleClick}>Click</Button>)
    
    fireEvent.click(screen.getByRole('button'))
    
    expect(handleClick).toHaveBeenCalledTimes(1)
  })

  it('is disabled when disabled prop is true', () => {
    render(<Button disabled>Click</Button>)
    expect(screen.getByRole('button')).toBeDisabled()
  })

  it('does not call onClick when disabled', () => {
    const handleClick = vi.fn()
    render(<Button type="button" onClick={handleClick} disabled>Click</Button>)
    
    fireEvent.click(screen.getByRole('button'))
    
    expect(handleClick).not.toHaveBeenCalled()
  })

  // Every variant is the Atelier button (.lv-btn): the variant only picks its tone
  it('renders with primary variant by default', () => {
    render(<Button>Primary</Button>)
    const button = screen.getByRole('button')
    expect(button.className).toContain('lv-btn')
    expect(button.className).toContain('is-primary')
  })

  it.each([
    ['secondary', []],
    ['outline', []],
    ['ghost', ['is-quiet']],
    ['danger', ['is-danger']],
    ['danger-soft', ['is-danger']],
    ['warning-soft', ['is-warn']],
    ['success', ['is-primary']],
  ])('renders the %s variant as the Atelier button', (variant, tones) => {
    render(<Button variant={variant}>V</Button>)
    const cls = screen.getByRole('button').className.split(/\s+/)
    expect(cls).toContain('lv-btn')
    for (const tone of tones) expect(cls).toContain(tone)
    for (const other of ['is-primary', 'is-quiet', 'is-danger', 'is-warn'].filter(c => !tones.includes(c))) {
      expect(cls).not.toContain(other)
    }
  })

  it('keeps the 32 px button for sm, default and lg, and the 26 px one for xs', () => {
    for (const size of ['sm', 'default', 'lg']) {
      const { unmount } = render(<Button size={size}>S</Button>)
      expect(screen.getByRole('button').className).not.toContain('is-small')
      unmount()
    }
    render(<Button size="xs">X</Button>)
    expect(screen.getByRole('button').className).toContain('is-small')
  })

  it('makes a lone named icon the square icon button, never a labelled one', () => {
    const Icon = () => <svg data-testid="i" />
    const { unmount } = render(<Button aria-label="Delete"><Icon /></Button>)
    expect(screen.getByRole('button', { name: 'Delete' }).className).toContain('is-icon')
    unmount()
    render(<Button aria-label="Delete"><Icon />Delete</Button>)
    expect(screen.getByRole('button').className).not.toContain('is-icon')
  })

  it('keeps no gradient or soft class of the previous interface', () => {
    for (const variant of ['primary', 'secondary', 'danger', 'success', 'danger-soft', 'warning-soft']) {
      const { unmount } = render(<Button variant={variant}>V</Button>)
      expect(screen.getByRole('button').className).not.toMatch(/btn-gradient|btn-soft|btn-danger-soft|btn-warning-soft|rounded-md/)
      unmount()
    }
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
