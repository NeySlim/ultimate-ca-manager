/**
 * The help dialog leads to the whole guide in a new tab, on the chapter of the page and the section
 * reached; its English text is a chunk of its own, loaded at the first opening.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'

const h = vi.hoisted(() => ({ evaluated: false }))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key, i18n: { language: 'en', resolvedLanguage: 'en' } }),
}))
vi.mock('../../../data/helpContent', () => ({
  helpContent: {
    acme: { title: 'Both', sections: [{ title: 'Q', content: 'q' }] },
    navigation: { title: 'Quick only', sections: [{ title: 'N', content: 'n' }] },
  },
}))
vi.mock('../../../data/helpGuides', () => {
  h.evaluated = true
  return {
    helpGuides: {
      acme: { title: 'Both guide', content: ['## First', 'one', '## Second', 'two', '## Third', 'three'].join('\n') },
      importExport: { title: 'Old', content: '## Old\ntext' },
    },
  }
})

import { HelpDialog } from '../HelpDialog'

Element.prototype.scrollIntoView = () => {}

const open = (pageKey) => render(<HelpDialog open onClose={() => {}} pageKey={pageKey} />)

describe('HelpDialog and the guide page', () => {
  it('leaves the English help out of the console until the dialog opens', async () => {
    expect(h.evaluated).toBe(false)
    open('acme')
    expect(await screen.findByTestId('help-dialog')).toBeTruthy()
    expect(h.evaluated).toBe(true)
  })

  it('opens the chapter of the page in a new tab, from the toolbar above the help', async () => {
    open('acme')
    const dialog = await screen.findByTestId('help-dialog')
    const link = await screen.findByRole('link', { name: 'guide.openInTab' })
    expect(link).toHaveAttribute('href', '/guide/acme')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link.getAttribute('rel')).toContain('noopener')
    // In the toolbar, after the views and the search, before the text; the foot keeps the way back only
    const bar = link.closest('.toolbar')
    expect(bar).toBeTruthy()
    expect(bar.lastElementChild).toBe(link)
    expect(bar.compareDocumentPosition(dialog.querySelector('.help-grid')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(link.closest('.modal-actions')).toBeNull()
    expect(within(dialog.querySelector('.modal-actions')).getAllByRole('button').map((b) => b.textContent)).toEqual(['help.back'])
  })

  it('keeps the button in the quick help tab', async () => {
    open('acme')
    fireEvent.click(await screen.findByRole('button', { name: 'help.quickHelp' }))
    expect(screen.getByRole('link', { name: 'guide.openInTab' }).closest('.toolbar')).toBeTruthy()
  })

  it('shows the toolbar with the button for a page that has only a quick help', async () => {
    open('navigation')
    const link = await screen.findByRole('link', { name: 'guide.openInTab' })
    expect(link).toHaveAttribute('href', '/guide/navigation')
    expect(link.closest('.toolbar')).toBeTruthy()
    expect(screen.queryByRole('group', { name: 'help.views' })).toBeNull()
  })

  it('carries the section reached from the contents line', async () => {
    open('acme')
    const dialog = await screen.findByTestId('help-dialog')
    fireEvent.click(within(dialog.querySelector('.help-toc')).getByRole('link', { name: 'Second' }))
    expect(screen.getByRole('link', { name: 'guide.openInTab' })).toHaveAttribute('href', '/guide/acme#acme-second')
  })

  it('offers no button for a page that has no chapter of its own', async () => {
    open('importExport')
    await screen.findByTestId('help-dialog')
    expect(screen.queryByRole('link', { name: 'guide.openInTab' })).toBeNull()
  })
})
