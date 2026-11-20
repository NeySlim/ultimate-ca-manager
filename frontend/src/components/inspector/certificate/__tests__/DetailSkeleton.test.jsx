/**
 * A certificate loading in the inspector shows the mockup's frame already: the heading at
 * its height, the section tabs in place but inert, and the bars inside the panel.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }) }))

import { DetailSkeleton } from '../DetailSkeleton'

describe('DetailSkeleton', () => {
  it('lays the section tabs of a certificate, the first one current, out of reach', () => {
    render(<DetailSkeleton sections={['overview', 'chain', 'extensions', 'history', 'pem']} />)
    const tabs = screen.getByTestId('inspector-skeleton-sections')
    expect(tabs).toHaveAttribute('aria-hidden', 'true')
    expect([...tabs.children].map((c) => c.textContent)).toEqual([
      'inspector.sections.overview', 'inspector.sections.chain', 'inspector.sections.extensions',
      'inspector.sections.history', 'inspector.sections.pem'])
    expect(tabs.children[0]).toHaveAttribute('data-current', 'true')
    expect(tabs.querySelector('button, [tabindex]')).toBeNull()
    expect(screen.getByTestId('inspector-skeleton').querySelector('.ins-panel .ins-sk-panel')).not.toBeNull()
    expect(screen.getByRole('status')).toHaveTextContent('common.loading')
  })

  it('keeps the plain bars for an object without sections', () => {
    render(<DetailSkeleton />)
    expect(screen.queryByTestId('inspector-skeleton-sections')).toBeNull()
    expect(screen.getByTestId('inspector-skeleton').querySelector('.ins-sk-panel')).not.toBeNull()
  })
})
