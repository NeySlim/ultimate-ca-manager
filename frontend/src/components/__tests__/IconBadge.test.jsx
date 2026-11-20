import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ShieldCheck, User, Certificate } from '@phosphor-icons/react'
import { IconBadge, IconAvatar } from '../IconBadge'

describe('IconBadge Component', () => {
  it('renders with icon', () => {
    const { container } = render(<IconBadge icon={ShieldCheck} />)
    expect(container.querySelector('svg')).toBeInTheDocument()
  })

  it('renders without icon', () => {
    const { container } = render(<IconBadge />)
    expect(container.querySelector('svg')).not.toBeInTheDocument()
  })

  it('applies default color (primary): the accent icon, no tile', () => {
    const { container } = render(<IconBadge icon={ShieldCheck} />)
    expect(container.firstChild.className).toContain('is-accent')
    expect(container.firstChild.className).not.toMatch(/bg-|rounded-xl/)
  })

  it('applies default size (md)', () => {
    const { container } = render(<IconBadge icon={ShieldCheck} />)
    expect(container.firstChild.className).toContain('w-10')
    expect(container.firstChild.className).toContain('h-10')
  })

  it('renders with different sizes', () => {
    const sizes = {
      table: 'w-6 h-6',
      xs: 'w-6 h-6',
      sm: 'w-8 h-8',
      md: 'w-10 h-10',
      lg: 'w-12 h-12',
      xl: 'w-14 h-14',
    }

    Object.entries(sizes).forEach(([size, expected]) => {
      const { container } = render(<IconBadge icon={ShieldCheck} size={size} />)
      const badge = container.firstChild
      expected.split(' ').forEach(cls => {
        expect(badge.className).toContain(cls)
      })
    })
  })

  // Bare icons in the tone of the mockup: accent, good, warn, bad, muted
  it.each([
    ['blue', 'is-accent'], ['violet', 'is-accent'], ['purple', 'is-accent'], ['teal', 'is-accent'], ['primary', 'is-accent'],
    ['emerald', 'is-good'], ['green', 'is-good'], ['success', 'is-good'],
    ['orange', 'is-warn'], ['amber', 'is-warn'], ['yellow', 'is-warn'], ['warning', 'is-warn'],
    ['danger', 'is-bad'],
  ])('draws %s in the %s tone, without a tile', (color, tone) => {
    const { container } = render(<IconBadge icon={ShieldCheck} color={color} />)
    expect(container.firstChild.className).toContain(tone)
    expect(container.firstChild.className).not.toMatch(/icon-bg-|bg-accent-|bg-bg-/)
  })

  it('draws neutral and unknown colours muted', () => {
    for (const color of ['slate', 'neutral', 'muted', 'unknown-color']) {
      const { container } = render(<IconBadge icon={ShieldCheck} color={color} />)
      expect(container.firstChild.className).not.toMatch(/is-(accent|good|warn|bad)/)
      expect(container.firstChild.className).toContain('ui-icon')
    }
  })

  it('applies custom className', () => {
    const { container } = render(<IconBadge icon={ShieldCheck} className="custom-class" />)
    expect(container.firstChild.className).toContain('custom-class')
  })

  it('applies custom iconClassName', () => {
    const { container } = render(<IconBadge icon={ShieldCheck} iconClassName="icon-custom" />)
    const svg = container.querySelector('svg')
    expect(svg.className.baseVal).toContain('icon-custom')
  })

  it('passes props to container', () => {
    render(<IconBadge icon={ShieldCheck} data-testid="icon-badge" />)
    expect(screen.getByTestId('icon-badge')).toBeInTheDocument()
  })
})

describe('IconAvatar Component', () => {
  it('renders with icon', () => {
    const { container } = render(<IconAvatar icon={User} />)
    expect(container.querySelector('svg')).toBeInTheDocument()
  })

  it('renders with initials', () => {
    render(<IconAvatar initials="JD" />)
    expect(screen.getByText('JD')).toBeInTheDocument()
  })

  it('prioritizes icon over initials', () => {
    const { container } = render(<IconAvatar icon={User} initials="JD" />)
    expect(container.querySelector('svg')).toBeInTheDocument()
    expect(screen.queryByText('JD')).not.toBeInTheDocument()
  })

  it('renders empty without icon or initials', () => {
    const { container } = render(<IconAvatar />)
    expect(container.querySelector('svg')).not.toBeInTheDocument()
    expect(container.firstChild.textContent).toBe('')
  })

  it('applies default color (violet) as the accent tone', () => {
    const { container } = render(<IconAvatar icon={User} />)
    expect(container.firstChild.className).toContain('is-accent')
  })

  it('is always rounded-full', () => {
    const { container } = render(<IconAvatar icon={User} />)
    expect(container.firstChild.className).toContain('rounded-full')
  })

  it('applies size classes', () => {
    const { container } = render(<IconAvatar icon={User} size="lg" />)
    expect(container.firstChild.className).toContain('w-12')
    expect(container.firstChild.className).toContain('h-12')
  })

  it('writes initials at 12 px whatever the size', () => {
    render(<IconAvatar initials="JD" size="xl" data-testid="avatar" />)
    expect(screen.getByTestId('avatar').className).toContain('text-xs')
  })

  it('applies custom className', () => {
    const { container } = render(<IconAvatar icon={User} className="custom-avatar" />)
    expect(container.firstChild.className).toContain('custom-avatar')
  })
})
