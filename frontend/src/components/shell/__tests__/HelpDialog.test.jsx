/**
 * The help of a page in the mockup's help(): a wide <dialog>, its sections in a .help-grid; the product's
 * Quick help and Guide behind a segmented switch, the guide's search and contents line, nothing lost.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, within, fireEvent } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (key === 'help.term' ? `${opts.term}: ` : key),
    i18n: { language: 'en', resolvedLanguage: 'en' },
  }),
}))
vi.mock('../../../data/helpContent', () => ({
  helpContent: {
    both: {
      title: 'Both title', subtitle: 'Both subtitle', overview: 'The overview text',
      sections: [
        { title: 'Plain', content: 'Section prose', items: ['A bare item', { label: 'Label', text: 'labelled text' }] },
        { title: 'Terms', definitions: [{ term: 'CRL', description: 'revocation list' }], example: 'openssl x509' },
      ],
      tips: ['A tip'], warnings: ['A warning'], related: ['Certificates'],
    },
    quickOnly: { title: 'Quick only', sections: [{ title: 'Only', content: 'only quick' }] },
  },
}))
vi.mock('../../../data/helpGuides', () => ({
  helpGuides: {
    both: {
      title: 'Both guide',
      content: [
        '## First', 'Intro with **bold**, `code` and *italic*.', '### Sub', '- one', '- two', '',
        '## Second', '1. step', '2. next', '> Tip: quoted', '```', 'code line', '```',
        '## Third', 'needle here',
      ].join('\n'),
    },
    guideOnly: { title: 'Guide only', content: 'No heading at all' },
    rich: { title: 'Rich', content: ['## Table', '| Operation | Online |', '|---|---|', '| Issue | **Blocked** |', '1. one', '   - nested', '2. two', '> ⚠ Careful'].join('\n') },
  },
}))

import { HelpDialog } from '../HelpDialog'

const show = (pageKey, props = {}) => render(<HelpDialog open onClose={props.onClose || vi.fn()} pageKey={pageKey} {...props} />)
const dialog = () => screen.getByTestId('help-dialog')
const heads = () => [...dialog().querySelectorAll('.help-grid > section > h3')].map((h) => h.textContent)

describe('HelpDialog', () => {
  it('is the mockup\'s wide dialog: title, subtitle, Back to the console that closes it', () => {
    const onClose = vi.fn()
    show('both', { onClose })
    expect(dialog().tagName).toBe('DIALOG')
    expect(dialog()).toHaveClass('wide')
    expect(within(dialog()).getByRole('heading', { level: 2 })).toHaveTextContent('Both title')
    expect(dialog().querySelector('.modal-head p')).toHaveTextContent('Both subtitle')
    const back = within(dialog()).getByRole('button', { name: 'help.back' })
    expect(back).toHaveClass('btn', 'primary')
    expect(back.closest('.modal-actions')).toBeTruthy()
    fireEvent.click(back)
    expect(onClose).toHaveBeenCalled()
  })

  it('opens on the guide when there is one, and switches to the quick help with the segmented control', () => {
    show('both')
    const group = within(dialog()).getByRole('group', { name: 'help.views' })
    expect(group).toHaveClass('segmented')
    const [quick, guide] = within(group).getAllByRole('button')
    expect(guide).toHaveAttribute('aria-pressed', 'true')
    expect(heads()).toEqual(['First', 'Second', 'Third'])
    fireEvent.click(quick)
    expect(quick).toHaveAttribute('aria-pressed', 'true')
    expect(heads()).toEqual(['help.overview', 'Plain', 'Terms', 'help.proTips', 'common.warnings', 'help.seeAlso'])
  })

  it('shows every part of the quick help: prose, items with their label, definitions, example, tips, warnings, see also', () => {
    show('quickOnly')
    expect(within(dialog()).queryByRole('group', { name: 'help.views' })).toBeNull()
    expect(heads()).toEqual(['Only'])
    document.body.innerHTML = ''
    show('both')
    fireEvent.click(within(dialog()).getByRole('button', { name: 'help.quickHelp' }))
    const grid = dialog().querySelector('.help-grid')
    expect(grid).toHaveTextContent('The overview text')
    const plain = grid.querySelectorAll('section')[1]
    expect(plain.querySelector('p')).toHaveTextContent('Section prose')
    expect([...plain.querySelectorAll('li')].map((li) => li.textContent)).toEqual(['A bare item', 'Label: labelled text'])
    expect(plain.querySelector('li strong')).toHaveTextContent('Label:')
    const terms = grid.querySelectorAll('section')[2]
    expect(terms.querySelector('dl.props dt')).toHaveTextContent('CRL')
    expect(terms.querySelector('dl.props dd')).toHaveTextContent('revocation list')
    expect(terms.querySelector('pre.code-preview')).toHaveTextContent('openssl x509')
    expect(grid).toHaveTextContent('A tip')
    expect(grid).toHaveTextContent('A warning')
    expect(grid).toHaveTextContent('Certificates')
  })

  it('renders the guide\'s markdown in the help vocabulary', () => {
    show('both')
    const [first, second] = dialog().querySelectorAll('.help-grid > section')
    expect(first.querySelector('p strong')).toHaveTextContent('bold')
    expect(first.querySelector('span.mono')).toHaveTextContent('code')
    expect(first.querySelector('em')).toHaveTextContent('italic')
    expect([...first.querySelectorAll('ul li')].map((li) => li.textContent)).toEqual(['one', 'two'])
    const sub = first.querySelector('h4')
    expect(sub).toHaveTextContent('Sub')
    expect(sub).toHaveAttribute('id', 'both-sub')
    expect(first.querySelector('h3')).toHaveAttribute('id', 'both-first')
    expect([...second.querySelectorAll('ol li')].map((li) => li.textContent)).toEqual(['step', 'next'])
    expect(second.querySelector('.notice')).toHaveTextContent('Tip: quoted')
    expect(second.querySelector('pre.code-preview')).toHaveTextContent('code line')
  })

  it('draws the guide\'s tables, nested lists and notices without their symbol', () => {
    show('rich')
    const section = dialog().querySelector('.help-grid > section')
    expect([...section.querySelectorAll('table.compare-table thead th')].map((th) => th.textContent)).toEqual(['Operation', 'Online'])
    expect([...section.querySelectorAll('tbody td')].map((td) => td.textContent)).toEqual(['Issue', 'Blocked'])
    expect(section.querySelectorAll(':scope > ol > li')).toHaveLength(2)
    expect(section.querySelector('ol > li > ul > li')).toHaveTextContent('nested')
    expect(section.querySelector('.notice.warn').textContent).toBe('Careful')
  })

  it('searches the guide: only the sections that hold the text, then a line when none does', () => {
    show('both')
    const field = within(dialog()).getByRole('searchbox', { name: 'help.searchLabel' })
    fireEvent.change(field, { target: { value: 'NEEDLE' } })
    expect(heads()).toEqual(['Third'])
    fireEvent.change(field, { target: { value: 'second' } })
    expect(heads()).toEqual(['Second'])
    fireEvent.change(field, { target: { value: 'nowhere at all' } })
    expect(dialog().querySelector('.help-grid')).toBeNull()
    expect(dialog()).toHaveTextContent('help.noMatch')
  })

  it('lists the guide\'s sections in a contents line whose links move to them', () => {
    show('both')
    const links = [...dialog().querySelectorAll('p.small a.text-link')]
    expect(links.map((a) => a.textContent)).toEqual(['First', 'Second', 'Third'])
    expect(links.map((a) => a.getAttribute('href'))).toEqual(['#both-first', '#both-second', '#both-third'])
    Element.prototype.scrollIntoView = vi.fn()
    fireEvent.click(links[2])
    expect(document.activeElement).toHaveTextContent('Third')
    expect(document.activeElement.tagName).toBe('H3')
  })

  it('shows a guide without headings as one section, with no search tabs to switch', () => {
    show('guideOnly')
    expect(dialog().querySelector('.help-grid')).toHaveTextContent('No heading at all')
    expect(within(dialog()).queryByRole('group', { name: 'help.views' })).toBeNull()
  })

  it('draws nothing when closed or for a page without help', () => {
    render(<HelpDialog open={false} onClose={vi.fn()} pageKey="both" />)
    render(<HelpDialog open onClose={vi.fn()} pageKey="none" />)
    expect(screen.queryByTestId('help-dialog')).toBeNull()
  })
})
