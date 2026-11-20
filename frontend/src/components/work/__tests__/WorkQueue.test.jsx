/**
 * WorkQueue: urgency groups, two-level rows, selection and bulk actions, folded
 * history; loading, error and empty states; no selection without a bulk action.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { Warning, Clock } from '@phosphor-icons/react'

const i18n = vi.hoisted(() => ({ current: null }))
vi.mock('react-i18next', () => ({ useTranslation: () => i18n.current, Trans: ({ i18nKey, values }) => i18n.current.t(i18nKey, values).replace(/<\/?\w+>/g, '') }))
import { frI18n } from './frI18n'
i18n.current = frI18n

import { WorkQueue, WorkButton } from '../WorkQueue'
import { loadCause } from '../loadCause'

const NOW = Date.now()
const HOUR = 3600000
const row = (id, title, hours, extra = {}) => ({
  id, title, kind: 'Approbation · CSR', facts: ['Demandée par alice il y a 3 h', 'Serveur TLS'],
  due: new Date(NOW + hours * HOUR), dueDate: 'date exacte', onOpen: vi.fn(),
  actions: (disabled) => <WorkButton disabled={disabled}>Approuver…</WorkButton>, ...extra,
})
const groups = (rows = [row(1, 'CSR à signer : a.example.com', 20), row(2, 'CSR à signer : b.example.com', 30)]) => [
  { id: 'overdue', label: 'En retard', icon: Warning, tone: 'bad', items: [] },
  { id: 'soon', label: 'À traiter sous 48 h', icon: Clock, tone: 'warn', items: rows },
  { id: 'later', label: 'Plus tard', icon: Clock, tone: '', items: [row(3, 'CSR à signer : c.example.com', 100)] },
]
const base = { hint: 'Cochez plusieurs demandes', empty: { title: 'Aucune demande en attente', text: 'Rien à faire.' } }

describe('WorkQueue', () => {
  it('shows only the groups that hold rows, with their counter', () => {
    render(<WorkQueue {...base} groups={groups()} />)
    const heads = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)
    expect(heads).toEqual(['À traiter sous 48 h2', 'Plus tard1'])
    expect(screen.queryByText('En retard')).toBeNull()
  })

  it('draws a row on two levels: subject and type, then the facts; the due date in the compact form', () => {
    render(<WorkQueue {...base} groups={groups()} />)
    const li = screen.getByText('CSR à signer : a.example.com').closest('li')
    expect(within(li).getByText('Approbation · CSR')).toHaveClass('wk-kind')
    expect(within(li).getByText('Demandée par alice il y a 3 h · Serveur TLS')).toBeInTheDocument()
    expect(within(li).getByText('dans 20 h')).toBeInTheDocument()
    expect(within(li).getByText('date exacte')).toBeInTheDocument()
    expect(li.querySelector('.wk-due')).toHaveClass('is-warn')
  })

  it('opens a row from its subject', () => {
    const rows = [row(1, 'CSR à signer : a.example.com', 20)]
    render(<WorkQueue {...base} groups={groups(rows)} />)
    fireEvent.click(screen.getByRole('button', { name: 'CSR à signer : a.example.com' }))
    expect(rows[0].onOpen).toHaveBeenCalled()
  })

  it('offers no selection without a bulk action (no right to act together)', () => {
    render(<WorkQueue {...base} groups={groups()} />)
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0)
    expect(screen.getByText('Cochez plusieurs demandes')).toBeInTheDocument()
  })

  it('keeps the empty check column without a right to select: heads and text keep the template\'s place', () => {
    const { container } = render(<WorkQueue {...base} groups={groups()} />)
    for (const el of container.querySelectorAll('.wk-group-head, .wk-row')) {
      expect(el.firstElementChild).toHaveClass('wk-check')
      expect(el.firstElementChild).toHaveAttribute('aria-hidden', 'true')
    }
    expect(container.querySelectorAll('.wk-row')).toHaveLength(3)
  })

  it('selects rows from the keyboard, swaps the hint for the bulk bar and disables the row actions', () => {
    const bulk = vi.fn((ids) => <WorkButton>Approuver… ({ids.join(',')})</WorkButton>)
    render(<WorkQueue {...base} groups={groups()} bulkActions={bulk} />)
    const box = screen.getByRole('checkbox', { name: 'Sélectionner CSR à signer : a.example.com' })
    box.focus()
    fireEvent.click(box)
    const bar = screen.getByRole('group', { name: 'Actions groupées' })
    expect(within(bar).getByText('1 élément sélectionné')).toBeInTheDocument()
    expect(within(bar).getByRole('button', { name: 'Approuver… (1)' })).toBeInTheDocument()
    expect(screen.queryByText('Cochez plusieurs demandes')).toBeNull()
    for (const b of screen.getAllByRole('button', { name: 'Approuver…' })) expect(b).toBeDisabled()
    fireEvent.click(within(bar).getByRole('button', { name: 'Annuler la sélection' }))
    expect(screen.queryByRole('group', { name: 'Actions groupées' })).toBeNull()
    for (const b of screen.getAllByRole('button', { name: 'Approuver…' })) expect(b).toBeEnabled()
  })

  it('selects a whole group from its head, clear until every row of it is ticked, as the mockup', () => {
    render(<WorkQueue {...base} groups={groups()} bulkActions={(ids) => <span>{ids.length} pris</span>} />)
    const all = screen.getByRole('checkbox', { name: 'Tout sélectionner : À traiter sous 48 h' })
    fireEvent.click(screen.getByRole('checkbox', { name: 'Sélectionner CSR à signer : a.example.com' }))
    expect(all.indeterminate).toBe(false)
    expect(all).not.toBeChecked()
    fireEvent.click(all)
    expect(screen.getByText('2 pris')).toBeInTheDocument()
    expect(screen.getByText('2 éléments sélectionnés')).toBeInTheDocument()
    fireEvent.click(all)
    expect(screen.queryByText('2 pris')).toBeNull()
  })

  it('drops from the selection a row that left the queue', () => {
    const bulk = (ids) => <span>{ids.join(',')} pris</span>
    const { rerender } = render(<WorkQueue {...base} groups={groups()} bulkActions={bulk} />)
    fireEvent.click(screen.getByRole('checkbox', { name: 'Tout sélectionner : À traiter sous 48 h' }))
    expect(screen.getByText('1,2 pris')).toBeInTheDocument()
    rerender(<WorkQueue {...base} groups={groups([row(2, 'CSR à signer : b.example.com', 30)])} bulkActions={bulk} />)
    expect(screen.getByText('2 pris')).toBeInTheDocument()
  })

  it('keeps a row out of the selection when it says so', () => {
    const rows = [row(1, 'a', 20, { selectable: false }), row(2, 'b', 30)]
    render(<WorkQueue {...base} groups={groups(rows)} bulkActions={() => null} />)
    expect(screen.queryByRole('checkbox', { name: 'Sélectionner a' })).toBeNull()
    expect(screen.getByRole('checkbox', { name: 'Sélectionner b' })).toBeInTheDocument()
  })

  it('keeps the check column of a row the user may not select, so its text lines up', () => {
    const rows = [row(1, 'a', 20, { selectable: false }), row(2, 'b', 30)]
    render(<WorkQueue {...base} groups={groups(rows)} bulkActions={() => null} />)
    const li = screen.getByText('a').closest('li')
    expect(li).not.toHaveClass('no-check')
    expect(li.querySelector('.wk-check')).toHaveAttribute('aria-hidden', 'true')
    expect(within(li).queryByRole('checkbox')).toBeNull()
  })

  it('keeps the check column in the head of a group whose rows may not be selected', () => {
    const rows = [row(1, 'a', 20, { selectable: false })]
    render(<WorkQueue {...base} groups={groups(rows)} bulkActions={() => null} />)
    const head = screen.getByRole('heading', { level: 2, name: /^À traiter sous 48 h/ }).closest('header')
    expect(head.querySelector('.wk-check')).toHaveAttribute('aria-hidden', 'true')
    expect(within(head).queryByRole('checkbox')).toBeNull()
  })

  it('gives the focus to the page title after Clear selection, as the mockup', async () => {
    render(
      <>
        <header className="lv-head"><h1>Approbations</h1></header>
        <WorkQueue {...base} groups={groups()} bulkActions={() => null} />
      </>,
    )
    fireEvent.click(screen.getByRole('checkbox', { name: 'Sélectionner CSR à signer : a.example.com' }))
    fireEvent.click(screen.getByRole('button', { name: 'Annuler la sélection' }))
    await waitFor(() => expect(screen.getByRole('heading', { level: 1 })).toHaveFocus())
  })

  it('folds the history, its toggle saying so', () => {
    render(<WorkQueue {...base} groups={groups()} history={{ label: 'Traitées récemment', count: 3, children: <p>passé</p> }} />)
    const toggle = screen.getByRole('button', { name: 'Traitées récemment3' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByText('passé').closest('[hidden]')).not.toBeNull()
    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('passé').closest('[hidden]')).toBeNull()
  })

  it('shows the empty sentence and its action when no group holds a row', () => {
    render(<WorkQueue {...base} groups={groups([]).map((g) => ({ ...g, items: [] }))} empty={{ ...base.empty, action: <a href="/policies">Voir les politiques</a> }} />)
    const empty = screen.getByTestId('work-empty')
    expect(within(empty).getByRole('heading', { name: 'Aucune demande en attente' })).toBeInTheDocument()
    expect(within(empty).getByText('Rien à faire.')).toBeInTheDocument()
    expect(within(empty).getByRole('link', { name: 'Voir les politiques' })).toBeInTheDocument()
  })

  it('shows a skeleton while loading, announced as busy', () => {
    render(<WorkQueue {...base} state="loading" groups={[]} />)
    const status = screen.getByRole('status')
    expect(status).toHaveAttribute('aria-busy', 'true')
    expect(status).toHaveTextContent('Chargement de la file…')
    expect(screen.queryByTestId('work-empty')).toBeNull()
  })

  it('draws its skeleton where the content comes: the hint line, two groups, the folded section', () => {
    const { container } = render(<WorkQueue {...base} state="loading" groups={[]} history={{ label: 'Traitées', count: 0, children: null }} />)
    const skel = container.querySelector('.wk-skel')
    expect(skel).toHaveClass('wk-view')
    expect(skel.querySelector(':scope > .wk-hint')).not.toBeNull()
    expect(skel.querySelectorAll(':scope > .wk-panel')).toHaveLength(3)
    expect(skel.querySelectorAll('.wk-group-head .wk-check')).toHaveLength(2)
    expect(skel.querySelector('.wk-history-toggle')).not.toBeNull()
  })

  it('gives its hint line the hint\'s own text, hidden under the bar, so it takes the same lines', () => {
    const { container } = render(<WorkQueue {...base} state="loading" groups={[]} />)
    const ghost = container.querySelector('.wk-skel > .wk-hint .wk-skel-ghost')
    expect(ghost).toHaveTextContent('Cochez plusieurs demandes')
    expect(ghost.closest('[aria-hidden="true"]')).not.toBeNull()
  })

  it('shows the error with a Retry button', () => {
    const onRetry = vi.fn()
    render(<WorkQueue {...base} state="error" groups={[]} error={{ title: 'Échec du chargement', text: 'HTTP 503', onRetry }} />)
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('Échec du chargement')
    expect(alert).toHaveTextContent('HTTP 503')
    fireEvent.click(within(alert).getByRole('button', { name: 'Réessayer' }))
    expect(onRetry).toHaveBeenCalled()
  })

  it('names the cause of a failed read as the mockup, with the journal for who may read it', () => {
    const err = Object.assign(new Error('Service indisponible'), { status: 503, request: 'GET /api/v2/approvals' })
    render(
      <MemoryRouter>
        <WorkQueue {...base} state="error" groups={[]}
          error={{ title: 'Impossible de charger les demandes d’approbation', cause: loadCause(err, frI18n.t), onRetry: () => {}, journal: '/audit' }} />
      </MemoryRouter>,
    )
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('Cause : le serveur a répondu 503 Service indisponible à GET /api/v2/approvals. Les autres vues et l’inspecteur restent utilisables.')
    expect(within(alert).getByRole('link', { name: 'Voir le journal' })).toHaveAttribute('href', '/audit')
  })

  it('says the request alone when the server did not answer, the message when there is no request', () => {
    expect(loadCause({ request: 'GET /api/v2/reports/schedule' }, frI18n.t)).toBeTruthy()
    expect(loadCause(new Error('réseau coupé'), frI18n.t)).toBe('Cause : réseau coupé. Les autres vues et l’inspecteur restent utilisables.')
    expect(loadCause(null, frI18n.t)).toBe('')
  })
})
