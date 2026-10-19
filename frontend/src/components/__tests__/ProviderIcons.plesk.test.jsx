import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { ProviderIcon, getProviderColor } from '../ProviderIcons'

describe('Plesk provider icon', () => {
  it('renders the brand logo and colour, not the fallback globe', () => {
    const { container } = render(<ProviderIcon type="plesk" />)
    expect(container.querySelector('svg title')?.textContent).toBe('Plesk')
    expect(getProviderColor('plesk')).toBe('#52BBE6')
  })
})
