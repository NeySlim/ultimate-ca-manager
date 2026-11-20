/**
 * WorkQueue: urgency groups, two-level rows, selection and bulk actions, folded
 * history; loading, error and empty states; no selection without a bulk action.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { Warning, Clock } from '@phosphor-icons/react'

const i18n = vi.hoisted(() => ({ current: null }))
vi.mock('react-i18next', () => ({ useTranslation: () => i18n.current }))
import { frI18n } from './frI18n'
i18n.current = frI18n

import { WorkQueue, WorkButton } from '../WorkQueue'

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

  it('selects a whole group from its head, half-selected when only some rows are', () => {
    render(<WorkQueue {...base} groups={groups()} bulkActions={(ids) => <span>{ids.length} pris</span>} />)
    const all = screen.getByRole('checkbox', { name: 'Tout sélectionner : À traiter sous 48 h' })
    fireEvent.click(screen.getByRole('checkbox', { name: 'Sélectionner CSR à signer : a.example.com' }))
    expect(all.indeterminate).toBe(true)
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

  it('shows the error with a Retry button', () => {
    const onRetry = vi.fn()
    render(<WorkQueue {...base} state="error" groups={[]} error={{ title: 'Échec du chargement', text: 'HTTP 503', onRetry }} />)
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('Échec du chargement')
    expect(alert).toHaveTextContent('HTTP 503')
    fireEvent.click(within(alert).getByRole('button', { name: 'Réessayer' }))
    expect(onRetry).toHaveBeenCalled()
  })
})
