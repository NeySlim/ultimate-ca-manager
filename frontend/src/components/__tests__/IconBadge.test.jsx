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

  it('applies default color (primary)', () => {
    const { container } = render(<IconBadge icon={ShieldCheck} />)
    expect(container.firstChild.className).toContain('bg-accent-primary')
  })

  it('applies default size (md)', () => {
    const { container } = render(<IconBadge icon={ShieldCheck} />)
    expect(container.firstChild.className).toContain('w-10')
    expect(container.firstChild.className).toContain('h-10')
  })

  it('renders with different sizes', () => {
    const sizes = {
      table: 'w-7 h-7',
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

  it('applies different colors', () => {
    const colors = ['blue', 'violet', 'emerald', 'teal', 'orange', 'amber']
    colors.forEach(color => {
      const { container } = render(<IconBadge icon={ShieldCheck} color={color} />)
      expect(container.firstChild.className).toContain(`icon-bg-${color}`)
    })
  })

  it('applies color aliases', () => {
    // purple -> violet
    const { container: c1 } = render(<IconBadge icon={ShieldCheck} color="purple" />)
    expect(c1.firstChild.className).toContain('icon-bg-violet')
    
    // green -> emerald
    const { container: c2 } = render(<IconBadge icon={ShieldCheck} color="green" />)
    expect(c2.firstChild.className).toContain('icon-bg-emerald')
    
    // yellow -> amber
    const { container: c3 } = render(<IconBadge icon={ShieldCheck} color="yellow" />)
    expect(c3.firstChild.className).toContain('icon-bg-amber')
  })

  it('applies semantic colors', () => {
    const semanticColors = ['primary', 'success', 'warning', 'danger']
    semanticColors.forEach(color => {
      const { container } = render(<IconBadge icon={ShieldCheck} color={color} />)
      expect(container.firstChild.className).toContain(`bg-accent-${color}`)
    })
  })

  it('applies neutral colors', () => {
    const neutralColors = ['slate', 'neutral', 'muted']
    neutralColors.forEach(color => {
      const { container } = render(<IconBadge icon={ShieldCheck} color={color} />)
      expect(container.firstChild.className).toContain('bg-bg-tertiary')
    })
  })

  it('falls back to neutral for unknown color', () => {
    const { container } = render(<IconBadge icon={ShieldCheck} color="unknown-color" />)
    expect(container.firstChild.className).toContain('bg-bg-tertiary')
  })

  it('applies different rounded values', () => {
    const roundedMap = {
      full: 'rounded-full',
      xl: 'rounded-xl',
      lg: 'rounded-lg',
      md: 'rounded-md',
      sm: 'rounded-sm',
      none: 'rounded-none',
    }

    Object.entries(roundedMap).forEach(([rounded, expected]) => {
      const { container } = render(<IconBadge icon={ShieldCheck} rounded={rounded} />)
      expect(container.firstChild.className).toContain(expected)
    })
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

  it('applies default color (violet)', () => {
    const { container } = render(<IconAvatar icon={User} />)
    expect(container.firstChild.className).toContain('icon-bg-violet')
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

  it('applies initials text size based on size prop', () => {
    const sizeMap = {
      xs: 'text-2xs',
      sm: 'text-xs',
      md: 'text-sm',
      lg: 'text-base',
      xl: 'text-lg',
    }

    Object.entries(sizeMap).forEach(([size, expected]) => {
      render(<IconAvatar initials="JD" size={size} data-testid={`avatar-${size}`} />)
      const avatar = screen.getByTestId(`avatar-${size}`)
      const span = avatar.querySelector('span')
      expect(span.className).toContain(expected)
    })
  })

  it('applies custom className', () => {
    const { container } = render(<IconAvatar icon={User} className="custom-avatar" />)
    expect(container.firstChild.className).toContain('custom-avatar')
  })
})
