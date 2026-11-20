import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Badge } from '../Badge'

describe('Badge Component', () => {
  it('renders children correctly', () => {
    render(<Badge>Active</Badge>)
    expect(screen.getByText('Active')).toBeInTheDocument()
  })

  // A badge is the mockup's .badge: the tone colours its text and icon, nothing fills it
  it.each([
    ['default', null], ['success', 'is-good'], ['warning', 'is-warn'], ['danger', 'is-bad'],
    ['info', 'is-accent'], ['secondary', 'is-muted'], ['outline', 'is-chip'],
  ])('renders the %s variant in its tone, without a fill', (variant, tone) => {
    render(<Badge variant={variant}>Label</Badge>)
    const cls = screen.getByText('Label').className
    expect(cls).toContain('lv-pill')
    if (tone) expect(cls).toContain(tone)
    expect(cls).not.toMatch(/status-\w+-bg|bg-tertiary|font-semibold|rounded-full/)
  })

  it('renders with icon', () => {
    render(
      <Badge variant="success">
        <span data-testid="icon">✓</span> Valid
      </Badge>
    )
    expect(screen.getByTestId('icon')).toBeInTheDocument()
  })

  it('keeps one 12 px size whatever size is asked', () => {
    for (const size of ['sm', 'default', 'lg']) {
      const { unmount } = render(<Badge size={size}>S</Badge>)
      expect(screen.getByText('S').className).not.toMatch(/text-(2xs|xs|sm)|px-/)
      unmount()
    }
  })

  it('applies custom className', () => {
    render(<Badge className="custom-class">Custom</Badge>)
    expect(screen.getByText('Custom').className).toContain('custom-class')
  })
})
