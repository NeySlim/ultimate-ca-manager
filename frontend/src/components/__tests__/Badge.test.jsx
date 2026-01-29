import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Badge } from '../Badge'

describe('Badge Component', () => {
  it('renders children correctly', () => {
    render(<Badge>Active</Badge>)
    expect(screen.getByText('Active')).toBeInTheDocument()
  })

  it('renders default variant', () => {
    render(<Badge>Default</Badge>)
    const badge = screen.getByText('Default')
    expect(badge.className).toContain('bg-bg-tertiary')
  })

  it('renders success variant', () => {
    render(<Badge variant="success">Valid</Badge>)
    const badge = screen.getByText('Valid')
    expect(badge.className).toContain('bg-green-500/12')
    expect(badge.className).toContain('text-green-400')
  })

  it('renders warning variant', () => {
    render(<Badge variant="warning">Expiring</Badge>)
    const badge = screen.getByText('Expiring')
    expect(badge.className).toContain('bg-yellow-500/12')
    expect(badge.className).toContain('text-yellow-400')
  })

  it('renders danger variant', () => {
    render(<Badge variant="danger">Revoked</Badge>)
    const badge = screen.getByText('Revoked')
    expect(badge.className).toContain('bg-red-500/12')
    expect(badge.className).toContain('text-red-400')
  })

  it('renders info variant', () => {
    render(<Badge variant="info">Pending</Badge>)
    const badge = screen.getByText('Pending')
    expect(badge.className).toContain('bg-blue-500/12')
    expect(badge.className).toContain('text-blue-400')
  })

  it('renders with icon', () => {
    render(
      <Badge variant="success">
        <span data-testid="icon">✓</span> Valid
      </Badge>
    )
    expect(screen.getByTestId('icon')).toBeInTheDocument()
  })

  it('renders small size correctly', () => {
    render(<Badge size="sm">Small</Badge>)
    const badge = screen.getByText('Small')
    expect(badge.className).toContain('px-1.5')
    expect(badge.className).toContain('text-[10px]')
  })

  it('renders large size correctly', () => {
    render(<Badge size="lg">Large</Badge>)
    const badge = screen.getByText('Large')
    expect(badge.className).toContain('px-2.5')
    expect(badge.className).toContain('text-sm')
  })

  it('applies custom className', () => {
    render(<Badge className="custom-class">Custom</Badge>)
    expect(screen.getByText('Custom').className).toContain('custom-class')
  })
})
