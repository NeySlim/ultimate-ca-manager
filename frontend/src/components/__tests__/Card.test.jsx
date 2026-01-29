import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { Card } from '../Card'

describe('Card Component', () => {
  it('renders children correctly', () => {
    render(<Card>Card Content</Card>)
    expect(screen.getByText('Card Content')).toBeInTheDocument()
  })

  it('applies custom className', () => {
    render(<Card className="custom-class">Content</Card>)
    const content = screen.getByText('Content')
    const card = content.closest('[class*="bg-gradient"]')
    expect(card.className).toContain('custom-class')
  })

  it('handles onClick', () => {
    const handleClick = vi.fn()
    render(<Card onClick={handleClick}>Clickable</Card>)
    
    fireEvent.click(screen.getByText('Clickable'))
    expect(handleClick).toHaveBeenCalledTimes(1)
  })

  it('renders with hover effect by default', () => {
    render(<Card>Content</Card>)
    const content = screen.getByText('Content')
    const card = content.closest('[class*="bg-gradient"]')
    expect(card.className).toContain('hover:')
  })

  it('disables hover effect when hover=false', () => {
    render(<Card hover={false}>Content</Card>)
    const content = screen.getByText('Content')
    const card = content.closest('[class*="bg-gradient"]')
    expect(card.className).not.toContain('hover:-translate')
  })

  it('applies glow effect when glow=true', () => {
    render(<Card glow={true}>Glowing</Card>)
    const content = screen.getByText('Glowing')
    const card = content.closest('[class*="bg-gradient"]')
    expect(card.className).toContain('ring-')
  })
})
