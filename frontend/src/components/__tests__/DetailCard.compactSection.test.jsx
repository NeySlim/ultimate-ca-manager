/**
 * A collapsible section is the mockup's bordered block: the title as written (no capitals
 * forced), no gradient header nor accent line, the toggle still exposed by aria-expanded.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key, i18n: { language: 'en', changeLanguage: () => {} } }),
}))
vi.mock('../../contexts', () => ({
  useMobile: () => ({ isMobile: false, isTablet: false, isDesktop: true }),
}))

import { CompactSection, DetailField } from '../DetailCard'

describe('CompactSection', () => {
  it('is a bordered block with its title in sentence case', () => {
    const { container } = render(<CompactSection title="Key usage" collapsible>body</CompactSection>)
    const root = container.firstChild
    expect(root.className).toContain('ui-compact')
    const heading = screen.getByRole('heading', { name: 'Key usage' })
    expect(heading.className).not.toMatch(/uppercase|tracking/)
    expect(container.querySelector('.section-header-gradient, .bg-accent-25')).toBeNull()
  })

  it('keeps its toggle', () => {
    render(<CompactSection title="Extensions" collapsible defaultOpen={false}>body</CompactSection>)
    const toggle = screen.getByRole('button', { name: 'Extensions' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
  })
})

describe('DetailField', () => {
  it('labels its value in normal case', () => {
    render(<dl><DetailField label="Serial" value="01:02" /></dl>)
    const term = screen.getByText('Serial')
    expect(term.tagName).toBe('DT')
    expect(term.className).not.toMatch(/uppercase/)
    expect(term.closest('.ui-detail-field')).not.toBeNull()
  })
})
