import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { Card } from '../Card'

describe('Card Component', () => {
  it('renders children correctly', () => {
    render(<Card>Card Content</Card>)
    expect(screen.getByText('Card Content')).toBeInTheDocument()
  })

  it('applies custom className', () => {
    const { container } = render(<Card className="custom-class">Content</Card>)
    const card = container.firstChild
    expect(card.className).toContain('custom-class')
  })

  it('handles onClick', () => {
    const handleClick = vi.fn()
    render(<Card onClick={handleClick}>Clickable</Card>)
    
    fireEvent.click(screen.getByText('Clickable'))
    expect(handleClick).toHaveBeenCalledTimes(1)
  })

  it('renders with default variant (card-soft)', () => {
    const { container } = render(<Card>Content</Card>)
    const card = container.firstChild
    expect(card.className).toContain('card-soft')
  })

  it('renders with elevated variant', () => {
    const { container } = render(<Card variant="elevated">Content</Card>)
    const card = container.firstChild
    expect(card.className).toContain('elevation-2')
  })

  it('applies accent border', () => {
    const { container } = render(<Card accent="primary">Accented</Card>)
    const card = container.firstChild
    expect(card.className).toContain('border-l-4')
    expect(card.className).toContain('border-l-accent-primary')
  })

  it('renders interactive card', () => {
    const { container } = render(<Card interactive>Interactive</Card>)
    const card = container.firstChild
    expect(card.className).toContain('card-interactive')
  })
})
