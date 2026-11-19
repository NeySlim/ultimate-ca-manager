/**
 * ResponsiveLayout: a page that hands it a total, an intent or views gets the
 * list template (page head, state tabs, panel); a page that does not keeps its
 * header, its Help button and its structure.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key, i18n: { language: 'en', changeLanguage: () => {} } }),
  Trans: ({ children }) => children,
}))
const device = vi.hoisted(() => ({ width: 1280 }))
vi.mock('../../../../contexts', () => ({
  useMobile: () => ({
    isMobile: device.width < 768, isTablet: false, isDesktop: device.width >= 768, isTouch: false,
    isLargeScreen: device.width >= 1280, screenWidth: device.width,
  }),
}))
vi.mock('../../FloatingHelpPanel', () => ({ FloatingHelpPanel: () => <div data-testid="help-panel" /> }))

import { ResponsiveLayout } from '../ResponsiveLayout'

const VIEWS = [
  { id: '', label: 'All', count: 12 },
  { id: 'valid', label: 'Valid', count: 9 },
  { id: 'expired', label: 'Expired', count: 3 },
]
const list = (props = {}) => render(
  <ResponsiveLayout
    title="Certificates" total="12 certificates" intent="Inspect, issue and maintain."
    actions={<button type="button">Issue</button>}
    views={VIEWS} activeView="valid" onViewChange={() => {}} viewsLabel="Filter by state"
    {...props}
  >
    <p>rows</p>
  </ResponsiveLayout>,
)

beforeEach(() => { device.width = 1280 })

describe('ResponsiveLayout as a list page', () => {
  it('shows the page head: title, total, intent, actions', () => {
    const { container } = list()
    const head = container.querySelector('header.lv-head')
    expect(within(head).getByRole('heading', { level: 1, name: 'Certificates' })).toBeInTheDocument()
    expect(head).toHaveTextContent('12 certificates')
    expect(head).toHaveTextContent('Inspect, issue and maintain.')
    expect(within(head).getByRole('button', { name: 'Issue' })).toBeInTheDocument()
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)
  })

  it('carries no Help button of its own, even with a help page', () => {
    list({ helpPageKey: 'certificates' })
    expect(screen.queryByRole('button', { name: 'common.help' })).toBeNull()
  })

  it('shows the views as tabs over the panel they filter', () => {
    const onViewChange = vi.fn()
    list({ onViewChange })
    const tabs = screen.getAllByRole('tab')
    expect(tabs.map((el) => el.textContent)).toEqual(['All12', 'Valid9', 'Expired3'])
    const panel = screen.getByRole('tabpanel')
    expect(panel).toHaveTextContent('rows')
    expect(panel).toHaveAttribute('aria-labelledby', tabs[1].id)
    tabs.forEach((el) => expect(el).toHaveAttribute('aria-controls', panel.id))
    fireEvent.click(tabs[2])
    expect(onViewChange).toHaveBeenCalledWith('expired')
  })

  it('names the panel by the tab list when no single view is on screen', () => {
    list({ activeView: null })
    const panel = screen.getByRole('tabpanel', { name: 'Filter by state' })
    expect(panel).not.toHaveAttribute('aria-labelledby')
  })

  it('is a page head alone when the page has no views', () => {
    list({ views: undefined })
    expect(screen.queryByRole('tablist')).toBeNull()
    expect(screen.queryByRole('tabpanel')).toBeNull()
    expect(screen.getByText('rows').parentElement).toHaveClass('lv-panel')
  })

  it('keeps the same head and tabs on a phone, with the actions once', () => {
    device.width = 390
    list()
    expect(screen.getByRole('heading', { level: 1, name: 'Certificates' })).toBeInTheDocument()
    expect(screen.getAllByRole('tab')).toHaveLength(3)
    expect(screen.getAllByRole('button', { name: 'Issue' })).toHaveLength(1)
  })
})

describe('ResponsiveLayout without the list props', () => {
  const plain = (props = {}) => render(
    <ResponsiveLayout title="Templates" subtitle="4 templates" actions={<button type="button">New</button>} helpPageKey="templates" {...props}>
      <p>rows</p>
    </ResponsiveLayout>,
  )

  it('keeps its header and its Help button, and none of the list template', () => {
    const { container } = plain()
    expect(container.querySelector('[class*="lv-"]')).toBeNull()
    expect(screen.queryByRole('tablist')).toBeNull()
    expect(screen.queryByRole('tabpanel')).toBeNull()
    expect(screen.getByText('Templates')).toBeInTheDocument()
    expect(screen.getByText('4 templates')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'New' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'common.help' })).toBeInTheDocument()
    // The page content is the direct child of main, as before
    expect(screen.getByText('rows').parentElement.tagName).toBe('MAIN')
  })

  it('keeps the stat tiles a page still hands it', () => {
    const onStatClick = vi.fn()
    plain({ stats: [{ label: 'Valid', value: 9, filterValue: 'valid' }], onStatClick })
    fireEvent.click(screen.getByText('Valid'))
    expect(onStatClick).toHaveBeenCalled()
  })

  it('keeps the action bar under the header on a phone', () => {
    device.width = 390
    const { container } = plain()
    expect(screen.getByRole('button', { name: 'New' })).toBeInTheDocument()
    expect(container.querySelector('header.lv-head')).toBeNull()
  })
})
