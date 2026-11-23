/**
 * The small gabarits of the Atelier mockup: buttons and their write mark, pills, page head, state
 * chips, active filters, empty and no-match blocks, read errors, table footer and page jump.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k, p) => (p ? `${k} ${JSON.stringify(p)}` : k), i18n: { language: 'fr' } }),
  Trans: ({ i18nKey, values }) => `${i18nKey} ${JSON.stringify(values)}`,
}))

import { Btn, IconBtn, TextLink } from '../Btn'
import { Pill } from '../Pill'
import { PageHead } from '../PageHead'
import { StateFilters } from '../StateFilters'
import { AppliedFilters } from '../AppliedFilters'
import { EmptyBlock, NoMatch } from '../EmptyBlock'
import { LoadError, LoadCause } from '../LoadError'
import { TableFooter } from '../TableFooter'
import { BatchBar } from '../BatchBar'

const wrap = (ui) => render(<MemoryRouter>{ui}</MemoryRouter>)

describe('buttons', () => {
  it('marks a primary or danger button as a write unless told otherwise', () => {
    wrap(<>
      <Btn tone="primary">A</Btn><Btn tone="danger">B</Btn><Btn tone="primary" write={false}>C</Btn>
      <Btn tone="quiet">D</Btn><Btn write>E</Btn><Btn>F</Btn>
    </>)
    const mark = (name) => screen.getByRole('button', { name }).getAttribute('data-write')
    expect([mark('A'), mark('B'), mark('C'), mark('D'), mark('E'), mark('F')]).toEqual(['', '', 'false', null, '', null])
    expect(screen.getByRole('button', { name: 'A' })).toHaveClass('btn', 'primary')
    expect(screen.getByRole('button', { name: 'F' })).toHaveAttribute('type', 'button')
  })
  it('draws a link as the button and an icon button named by its label', () => {
    wrap(<><Btn to="/x" tone="primary" icon="plus">Go</Btn><IconBtn icon="more" label="More" quiet /><IconBtn icon="close" label="Close" title={false} /><TextLink icon="right">See</TextLink></>)
    expect(screen.getByRole('link', { name: 'Go' })).toHaveAttribute('href', '/x')
    expect(screen.getByRole('link', { name: 'Go' })).toHaveAttribute('data-write', '')
    expect(screen.getByRole('button', { name: 'More' })).toHaveClass('icon-btn', 'quiet')
    expect(screen.getByRole('button', { name: 'More' })).toHaveAttribute('title', 'More')
    expect(screen.getByRole('button', { name: 'Close' })).not.toHaveAttribute('title')
    expect(screen.getByRole('button', { name: 'See' })).toHaveClass('text-link')
  })
})

describe('pill and page head', () => {
  it('gives each tone its icon, so the colour is never the only signal', () => {
    const { container } = render(<><Pill label="Valide" tone="good" /><Pill label="Échu" tone="bad" /></>)
    const pills = container.querySelectorAll('.badge')
    expect(pills[0]).toHaveClass('good')
    expect(pills[0].querySelector('svg').innerHTML).not.toBe(pills[1].querySelector('svg').innerHTML)
  })
  it('draws the title for the focus after a navigation, the total, the intent and the actions', () => {
    const { container } = render(<PageHead title="Certificats" total="46 identités" intent="Inspecter." actions={<button type="button">Émettre</button>} />)
    const h1 = screen.getByRole('heading', { level: 1, name: 'Certificats' })
    expect(h1).toHaveAttribute('id', 'main-title')
    expect(h1).toHaveAttribute('tabindex', '-1')
    expect(container.querySelector('.total')).toHaveTextContent('46 identités')
    expect(container.querySelector('.page-head .actions')).toContainElement(screen.getByRole('button', { name: 'Émettre' }))
  })
})

describe('state chips', () => {
  const views = [{ id: '', label: 'Tous', count: 46 }, { id: 'expiring', label: 'À renouveler', count: 1200, warn: true }]
  it('presses the active state and reports a choice', () => {
    const onChange = vi.fn()
    const { container } = render(<StateFilters views={views} active="" onChange={onChange} label="Filtrer par état" aside="Référence" />)
    const group = screen.getByRole('group', { name: 'Filtrer par état' })
    const [all, exp] = within(group).getAllByRole('button')
    expect(all).toHaveAttribute('aria-pressed', 'true')
    expect(exp).toHaveAttribute('aria-pressed', 'false')
    expect(exp.querySelector('.dot.warn')).not.toBeNull()
    expect(exp.querySelector('.counter').textContent).toBe(new Intl.NumberFormat('fr').format(1200))
    fireEvent.click(exp)
    expect(onChange).toHaveBeenCalledWith('expiring')
    expect(container.querySelector('.active-filters')).toHaveTextContent('Référence')
  })
  it('stands a bar for each counter while they are read', () => {
    const { container } = render(<StateFilters views={views} active="" label="x" busy />)
    expect(container.querySelectorAll('.counter .sk.sk-num')).toHaveLength(2)
  })
})

describe('active filters', () => {
  it('draws nothing without a chip or a note', () => {
    const { container } = render(<AppliedFilters chips={[]} />)
    expect(container).toBeEmptyDOMElement()
  })
  it('removes a chip by its own button and clears them all once there are two', () => {
    const a = vi.fn(); const b = vi.fn(); const all = vi.fn()
    render(<AppliedFilters chips={[{ key: 'due', label: 'Échéance', onRemove: a }, { key: 'check', label: 'Conformité', onRemove: b }]} note="Hors révoqués." onClearAll={all} />)
    const group = screen.getByRole('group', { name: 'table.activeFilters' })
    fireEvent.click(within(group).getByRole('button', { name: 'table.removeFilter {"label":"Conformité"}' }))
    expect(b).toHaveBeenCalled()
    expect(a).not.toHaveBeenCalled()
    fireEvent.click(within(group).getByRole('button', { name: 'table.clearFilters' }))
    expect(all).toHaveBeenCalled()
    expect(group).toHaveTextContent('Hors révoqués.')
  })
  it('offers no clear-all link for a single chip', () => {
    render(<AppliedFilters chips={[{ key: 'due', label: 'Échéance', onRemove: () => {} }]} onClearAll={() => {}} />)
    expect(screen.queryByRole('button', { name: 'table.clearFilters' })).toBeNull()
  })
})

describe('empty, no match and read error', () => {
  it('says why the list is empty and gives the next action, held by the write guard', () => {
    const onClick = vi.fn()
    const { container } = wrap(<EmptyBlock id="certificates" icon="cert" title="Aucun certificat" text="Pourquoi." action={{ label: 'Émettre', onClick, primary: true }} />)
    expect(container.querySelector('#empty-certificates.empty.empty-hint')).not.toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Émettre' }))
    expect(onClick).toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Émettre' })).toHaveAttribute('data-write', '')
  })
  it('resets the filters from the no-match block, and offers nothing to reset when nothing narrows', () => {
    const onReset = vi.fn()
    const { rerender } = render(<NoMatch title="Rien" text="Modifiez." resetLabel="Réinitialiser" onReset={onReset} />)
    fireEvent.click(screen.getByRole('button', { name: 'Réinitialiser' }))
    expect(onReset).toHaveBeenCalled()
    rerender(<NoMatch title="Rien" resetLabel="Réinitialiser" />)
    expect(screen.queryByRole('button')).toBeNull()
  })
  it('names the cause by status and request, the request alone, else the message', () => {
    const { rerender, container } = render(<LoadCause error={{ status: 503, request: 'GET /x' }} />)
    expect(container).toHaveTextContent('work.cause.status')
    expect(container).toHaveTextContent('"request":"GET /x"')
    rerender(<LoadCause error={{ request: 'GET /x' }} />)
    expect(container).toHaveTextContent('work.cause.noAnswer')
    rerender(<LoadCause error={{ message: 'boom' }} />)
    expect(container).toHaveTextContent('work.cause.message {"message":"boom"}')
  })
  it('retries a read that failed, and links to the journal only for who may read it', () => {
    const onRetry = vi.fn()
    const { rerender } = wrap(<LoadError id="certificates" title="Impossible" cause="Cause" onRetry={onRetry} journal="/audit" />)
    const alert = screen.getByRole('alert')
    expect(alert).toHaveAttribute('id', 'load-error-certificates')
    fireEvent.click(within(alert).getByRole('button', { name: 'table.retry' }))
    expect(onRetry).toHaveBeenCalled()
    expect(within(alert).getByRole('button', { name: 'table.retry' })).toHaveAttribute('data-write', 'false')
    expect(within(alert).getByRole('link', { name: 'work.viewLog' })).toHaveAttribute('href', '/audit')
    rerender(<MemoryRouter><LoadError id="certificates" title="Impossible" onRetry={onRetry} /></MemoryRouter>)
    expect(screen.queryByRole('link')).toBeNull()
  })
})

describe('table footer', () => {
  it('pages back and forth within bounds and changes the page size', () => {
    const onPage = vi.fn(); const onPerPage = vi.fn()
    render(<TableFooter range="1–12 sur 46" pagination={{ page: 1, pages: 4, perPage: 12, sizes: [12, 24, 50], onPage, onPerPage, perPageLabel: 'Par page' }} />)
    expect(screen.getByRole('button', { name: 'table.previousPage' })).toBeDisabled()
    expect(screen.getByText('1 / 4')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'table.nextPage' }))
    expect(onPage).toHaveBeenCalledWith(2)
    fireEvent.change(screen.getByRole('combobox', { name: 'Par page' }), { target: { value: '24' } })
    expect(onPerPage).toHaveBeenCalledWith(24)
  })
  it('jumps to a typed page, bounded to the pages, by Enter or Aller', () => {
    const onPage = vi.fn()
    render(<TableFooter range="r" pagination={{ page: 2, pages: 5, perPage: 25, onPage, jump: true }} />)
    const field = screen.getByRole('spinbutton')
    expect(field).toHaveValue(2)
    fireEvent.change(field, { target: { value: '9' } })
    fireEvent.keyDown(field, { key: 'Enter' })
    expect(onPage).toHaveBeenLastCalledWith(5)
    fireEvent.change(field, { target: { value: '3' } })
    fireEvent.click(screen.getByRole('button', { name: 'table.goToPage' }))
    expect(onPage).toHaveBeenLastCalledWith(3)
    expect(screen.getByRole('button', { name: 'table.nextPage' })).not.toBeDisabled()
  })
  it('gives each table its own page size field, each named by its label', () => {
    const pagination = (perPageLabel) => ({ page: 1, pages: 2, perPage: 25, onPage: vi.fn(), onPerPage: vi.fn(), perPageLabel })
    const { container } = render(<>
      <TableFooter range="a" pagination={pagination('Webhooks par page')} />
      <TableFooter range="b" pagination={pagination('Clés par page')} />
    </>)
    const fields = [...container.querySelectorAll('select.page-size')]
    expect(fields).toHaveLength(2)
    expect(fields[0].id).toBeTruthy()
    expect(fields[0].id).not.toBe(fields[1].id)
    expect(container.querySelectorAll('[id="page-size"]')).toHaveLength(0)
    expect(screen.getByRole('combobox', { name: 'Webhooks par page' })).toBe(fields[0])
    expect(screen.getByRole('combobox', { name: 'Clés par page' })).toBe(fields[1])
  })
  it('says the range and a note when the list is not paged', () => {
    const { container } = render(<TableFooter range="5 sur 5 modèles" note="Données" />)
    expect(container.querySelectorAll('footer.table-footer > span')).toHaveLength(2)
  })
})

describe('selection bar', () => {
  it('clears the selection and gives the focus to the page title', async () => {
    const onClear = vi.fn()
    render(<><h1 id="main-title" tabIndex={-1}>T</h1><BatchBar count="2 sélectionnés" onClear={onClear}><button type="button">Comparer</button></BatchBar></>)
    expect(screen.getByRole('group', { name: 'table.selection' })).toHaveTextContent('2 sélectionnés')
    fireEvent.click(screen.getByRole('button', { name: 'table.clearSelection' }))
    expect(onClear).toHaveBeenCalled()
    await new Promise((r) => requestAnimationFrame(r))
    expect(document.activeElement).toBe(screen.getByRole('heading', { name: 'T' }))
  })
})
