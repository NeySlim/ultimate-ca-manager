import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ShieldCheck } from '@phosphor-icons/react'
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

  it('renders with bordered variant', () => {
    const { container } = render(<Card variant="bordered">Content</Card>)
    const card = container.firstChild
    expect(card.className).toContain('border-2')
  })

  it('renders with soft variant (same as default)', () => {
    const { container } = render(<Card variant="soft">Content</Card>)
    const card = container.firstChild
    expect(card.className).toContain('card-soft')
  })

  it('applies different accent colors', () => {
    const colors = ['success', 'warning', 'danger', 'info', 'purple']
    colors.forEach(color => {
      const { container } = render(<Card accent={color}>Content</Card>)
      const card = container.firstChild
      expect(card.className).toContain(`border-l-accent-${color === 'info' ? 'primary' : color}`)
    })
  })
})

describe('Card.Header', () => {
  it('renders with title and subtitle', () => {
    render(
      <Card>
        <Card.Header title="Test Title" subtitle="Test Subtitle" />
      </Card>
    )
    expect(screen.getByText('Test Title')).toBeInTheDocument()
    expect(screen.getByText('Test Subtitle')).toBeInTheDocument()
  })

  it('renders with icon', () => {
    render(
      <Card>
        <Card.Header icon={ShieldCheck} title="Security" />
      </Card>
    )
    expect(screen.getByText('Security')).toBeInTheDocument()
  })

  it('renders with action element', () => {
    render(
      <Card>
        <Card.Header title="Title" action={<button>Action</button>} />
      </Card>
    )
    expect(screen.getByRole('button', { name: 'Action' })).toBeInTheDocument()
  })

  it('renders children when no icon/title', () => {
    render(
      <Card>
        <Card.Header>Custom Header Content</Card.Header>
      </Card>
    )
    expect(screen.getByText('Custom Header Content')).toBeInTheDocument()
  })

  it('applies custom className', () => {
    const { container } = render(
      <Card>
        <Card.Header className="custom-header" title="Title" />
      </Card>
    )
    expect(container.querySelector('.custom-header')).toBeInTheDocument()
  })
})

describe('Card.Body', () => {
  it('renders children', () => {
    render(
      <Card>
        <Card.Body>Body Content</Card.Body>
      </Card>
    )
    expect(screen.getByText('Body Content')).toBeInTheDocument()
  })

  it('applies custom className', () => {
    const { container } = render(
      <Card>
        <Card.Body className="custom-body">Content</Card.Body>
      </Card>
    )
    expect(container.querySelector('.custom-body')).toBeInTheDocument()
  })
})

describe('Card.Footer', () => {
  it('renders children', () => {
    render(
      <Card>
        <Card.Footer>Footer Content</Card.Footer>
      </Card>
    )
    expect(screen.getByText('Footer Content')).toBeInTheDocument()
  })

  it('applies custom className', () => {
    const { container } = render(
      <Card>
        <Card.Footer className="custom-footer">Content</Card.Footer>
      </Card>
    )
    expect(container.querySelector('.custom-footer')).toBeInTheDocument()
  })
})
