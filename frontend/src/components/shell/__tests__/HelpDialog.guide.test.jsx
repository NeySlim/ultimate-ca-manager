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
vi.mock('../../../data/helpContent', () => ({ helpContent: { acme: { title: 'Both', sections: [{ title: 'Q', content: 'q' }] } } }))
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

  it('opens the chapter of the page in a new tab', async () => {
    open('acme')
    const link = await screen.findByRole('link', { name: 'guide.openInTab' })
    expect(link).toHaveAttribute('href', '/guide/acme')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link.getAttribute('rel')).toContain('noopener')
    expect(link.closest('.modal-actions')).toBeTruthy()
  })

  it('carries the section reached from the contents line', async () => {
    open('acme')
    const dialog = await screen.findByTestId('help-dialog')
    fireEvent.click(within(dialog.querySelector('.help-toc')).getByRole('link', { name: 'Second' }))
    expect(screen.getByRole('link', { name: 'guide.openInTab' })).toHaveAttribute('href', '/guide/acme#acme-second')
  })

  it('opens the guide at its start for a page with no chapter of its own', async () => {
    open('importExport')
    expect(await screen.findByRole('link', { name: 'guide.openInTab' })).toHaveAttribute('href', '/guide')
  })
})
