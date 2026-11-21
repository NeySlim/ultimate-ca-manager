/**
 * The module templates of the Atelier mockup: the list and detail page (listView), the work queue
 * (workView, its groups, rows, selection and history), and the overview card with its menu.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'

const size = vi.hoisted(() => ({ isMobile: false }))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k, p) => (p ? `${k} ${JSON.stringify(p)}` : k), i18n: { language: 'fr' } }),
}))
vi.mock('../../../contexts/MobileContext', () => ({ useMobile: () => ({ isMobile: size.isMobile }) }))

import { ListView } from '../ListView'
import { WorkView } from '../WorkView'
import { Card } from '../Card'
import { Pill } from '../Pill'

beforeEach(() => { size.isMobile = false })

describe('the list and detail template', () => {
  const rows = [{ id: 'tls', name: 'Serveur TLS', cas: 'Services CA', days: '90 j', key: 'ECDSA', csr: 'Oui', state: 'Actif' }]
  const props = (extra = {}) => ({
    filters: { views: [{ id: '', label: 'Tous', count: 1 }, { id: 'a', label: 'Actif', count: 1 }], active: '', onChange: vi.fn(), label: 'Filtrer par état', aside: 'Référence' },
    label: 'Modèles', icon: 'template', rows, title: (r) => r.name, status: (r) => <Pill label={r.state} tone="good" />,
    columns: [{ label: 'Autorités', cell: (r) => r.cas, grow: true }, { label: 'Validité', cell: (r) => r.days }, { label: 'Clé', cell: (r) => r.key, muted: true }, { label: 'CSR', cell: (r) => r.csr }, { status: true }],
    onOpen: vi.fn(), footer: { range: '1 sur 1 modèle', note: 'Note' }, ...extra,
  })
  it('draws the state chips, the name first, the state column, the chevron that opens the detail, and the footer', () => {
    const p = props({ openedId: 'tls' })
    const { container } = render(<ListView {...p} />)
    expect(screen.getByRole('group', { name: 'Filtrer par état' })).toBeInTheDocument()
    expect(container.querySelector('section.table-workspace.module-workspace')).toHaveAttribute('aria-label', 'Modèles')
    expect(screen.getAllByRole('columnheader').map((h) => h.textContent)).toEqual(['atelier.name', 'Autorités', 'Validité', 'Clé', 'CSR', 'atelier.state', 'common.actions'])
    expect(container.querySelector('#module-scroll')).toHaveAttribute('aria-label', 'atelier.tableOf {"name":"Modèles"}')
    expect(container.querySelector('tbody tr')).toHaveClass('opened')
    expect(container.querySelector('td.muted')).toHaveTextContent('ECDSA')
    fireEvent.click(screen.getByRole('button', { name: 'atelier.openDetail {"name":"Serveur TLS"}' }))
    fireEvent.click(screen.getByRole('button', { name: 'Serveur TLS' }))
    expect(p.onOpen).toHaveBeenCalledTimes(2)
    expect([...container.querySelectorAll('footer.table-footer span')].map((s) => s.textContent)).toEqual(['1 sur 1 modèle', 'Note'])
  })
  it('shows on a phone the first three facts and the state on each record', () => {
    size.isMobile = true
    const { container } = render(<ListView {...props()} />)
    const rec = container.querySelector('article.mobile-record')
    expect([...rec.querySelectorAll('.row-meta > span')].map((s) => s.textContent)).toEqual(['Services CA', '90 j', 'ECDSA'])
    expect(rec.querySelector('.row-status')).toHaveTextContent('Actif')
  })
  it('puts a read error in place of the table, the chips staying', () => {
    render(<ListView {...props({ error: <div role="alert">Impossible</div> })} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Impossible')
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.getByRole('group', { name: 'Filtrer par état' })).toBeInTheDocument()
  })
})

describe('the work queue', () => {
  const row = (id, title, extra = {}) => ({ id, title, kind: 'Approbation · CSR', facts: ['Demandée par alice', 'Serveur TLS', null], due: new Date(Date.now() + 20 * 3600000), dueLabel: 'dans 20 h', dueDate: '9 nov.', tone: 'warn', onOpen: vi.fn(),
    actions: (off) => <button type="button" className="btn" disabled={off}>{`Approuver ${title}`}</button>, ...extra })
  const groups = (rows) => [{ id: 'overdue', label: 'En retard', icon: 'warning', tone: 'bad', items: [] }, { id: 'soon', label: 'Sous 48 h', icon: 'clock', tone: 'warn', items: rows }]
  const base = { hint: 'Cochez plusieurs demandes', empty: { title: 'Aucune demande', text: 'Rien.' } }
  it('draws the groups that have rows, each row with its kind, facts and due date', () => {
    const { container } = render(<WorkView {...base} groups={groups([row('a', 'CSR a'), row('b', 'CSR b')])} openedId="b" />)
    expect(container.querySelectorAll('section.panel.work-group')).toHaveLength(1)
    expect(container.querySelector('#wg-soon')).toHaveTextContent('Sous 48 h2')
    const first = container.querySelector('li.work-row')
    expect(first.querySelector('.work-detail')).toHaveTextContent('Demandée par alice · Serveur TLS')
    expect(first.querySelector('.queue-due.warn strong')).toHaveTextContent('dans 20 h')
    expect(container.querySelectorAll('li.work-row')[1]).toHaveClass('opened')
    expect(screen.getByText('Cochez plusieurs demandes').closest('p')).toHaveClass('work-hint')
    expect(screen.queryByRole('checkbox')).toBeNull()
  })
  it('selects rows and groups for the bulk actions, the row actions waiting meanwhile', async () => {
    const bulk = vi.fn((ids) => <button type="button">{`Approuver ${ids.length}`}</button>)
    render(<><h1 id="main-title" tabIndex={-1}>T</h1><WorkView {...base} groups={groups([row('a', 'CSR a'), row('b', 'CSR b')])} bulk={bulk} /></>)
    fireEvent.click(screen.getByRole('checkbox', { name: 'work.selectRow {"name":"CSR a"}' }))
    expect(screen.getByRole('group', { name: 'work.bulkLabel' })).toHaveTextContent('work.selected {"count":1}')
    expect(screen.getByRole('button', { name: 'Approuver CSR b' })).toBeDisabled()
    const all = screen.getByRole('checkbox', { name: 'work.selectAll {"group":"Sous 48 h"}' })
    expect(all).not.toBeChecked()
    fireEvent.click(all)
    expect(screen.getByRole('button', { name: 'Approuver 2' })).toBeInTheDocument()
    expect(all).toBeChecked()
    fireEvent.click(screen.getByRole('button', { name: 'table.clearSelection' }))
    expect(screen.queryByRole('group', { name: 'work.bulkLabel' })).toBeNull()
    await new Promise((r) => requestAnimationFrame(r))
    expect(document.activeElement).toHaveTextContent('T')
  })
  it('lets a selected row that left the queue leave the selection', () => {
    const bulk = (ids) => <span>{`n=${ids.length}`}</span>
    const { rerender } = render(<WorkView {...base} groups={groups([row('a', 'CSR a'), row('b', 'CSR b')])} bulk={bulk} />)
    fireEvent.click(screen.getByRole('checkbox', { name: 'work.selectAll {"group":"Sous 48 h"}' }))
    expect(screen.getByText('n=2')).toBeInTheDocument()
    rerender(<WorkView {...base} groups={groups([row('b', 'CSR b')])} bulk={bulk} />)
    expect(screen.getByText('n=1')).toBeInTheDocument()
  })
  it('keeps the check column of a row that cannot be selected, empty', () => {
    const { container } = render(<WorkView {...base} groups={groups([row('a', 'CSR a', { selectable: false }), row('b', 'CSR b')])} bulk={() => null} />)
    const [a, b] = container.querySelectorAll('li.work-row')
    expect(a.querySelector('label.check-hit input')).toBeNull()
    expect(b.querySelector('label.check-hit input')).not.toBeNull()
  })
  it('folds the history and opens it on demand', () => {
    render(<WorkView {...base} groups={groups([row('a', 'CSR a')])} history={{ label: 'Traitées', count: 1, children: [<li key="1">DEM-1</li>] }} />)
    const toggle = screen.getByRole('button', { name: /Traitées/ })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(document.getElementById('work-history')).toHaveAttribute('hidden')
    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(document.getElementById('work-history')).not.toHaveAttribute('hidden')
    expect(screen.getByText('DEM-1')).toBeInTheDocument()
  })
  it('says the queue is empty with its action, shows skeletons while loading, an error in place of the queue', () => {
    const { rerender, container } = render(<WorkView {...base} empty={{ ...base.empty, action: <button type="button">Politiques</button> }} groups={groups([])} />)
    expect(screen.getByTestId('work-empty')).toHaveTextContent('Aucune demande')
    expect(screen.getByRole('button', { name: 'Politiques' })).toBeInTheDocument()
    rerender(<WorkView {...base} state="loading" groups={groups([])} history={{ label: 'x', count: 0 }} />)
    expect(container.querySelector('.work-view')).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByRole('status')).toHaveTextContent('work.loading')
    rerender(<WorkView {...base} state="error" error={<div role="alert">Erreur</div>} groups={groups([])} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Erreur')
  })
})

describe('the overview card', () => {
  it('draws its title, counter, sentence and tools, and opens its menu on its first item', () => {
    const onHide = vi.fn()
    const { container } = render(<Card id="activity" title="Dernières opérations" count={3} sub="Journal" tools={<a href="/audit">Tout voir</a>} onHide={onHide} onCustomize={() => {}}><p>corps</p></Card>)
    const card = container.querySelector('section.panel.dash-card.card-activity#card-activity')
    expect(card).toHaveAttribute('aria-labelledby', 'card-activity-title')
    expect(screen.getByRole('heading', { name: 'Dernières opérations3' })).toHaveAttribute('tabindex', '-1')
    const button = screen.getByRole('button', { name: 'atelier.cardOptions {"name":"Dernières opérations"}' })
    expect(document.getElementById('card-menu-activity')).toHaveAttribute('hidden')
    fireEvent.click(button)
    expect(button).toHaveAttribute('aria-expanded', 'true')
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'atelier.hideCard' }))
    fireEvent.click(screen.getByRole('button', { name: 'atelier.hideCard' }))
    expect(onHide).toHaveBeenCalled()
    expect(document.getElementById('card-menu-activity')).toHaveAttribute('hidden')
  })
  it('closes its menu on Escape, back on its button, and on a click elsewhere', () => {
    render(<><p>dehors</p><Card id="q" title="File" onHide={() => {}} /></>)
    const button = screen.getByRole('button', { name: 'atelier.cardOptions {"name":"File"}' })
    fireEvent.click(button)
    fireEvent.keyDown(document.activeElement, { key: 'Escape' })
    expect(button).toHaveAttribute('aria-expanded', 'false')
    expect(document.activeElement).toBe(button)
    fireEvent.click(button)
    fireEvent.pointerDown(screen.getByText('dehors'))
    expect(button).toHaveAttribute('aria-expanded', 'false')
  })
  it('has no menu when the page offers neither item', () => {
    render(<Card id="q" title="File" />)
    expect(screen.queryByRole('button')).toBeNull()
  })
})
