/**
 * A report in the inspector, through the shared InspectorObject: heading, the
 * Report, Runs and Preview sections, the certificates it lists, its actions by right.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const stable = vi.hoisted(() => ({ i18n: null, perms: [] }))
vi.mock('react-i18next', () => ({ useTranslation: () => stable.i18n, Trans: ({ children }) => children, initReactI18next: { type: '3rdParty', init: () => {} } }))
import { frI18n } from '../../../components/work/__tests__/frI18n'
stable.i18n = frI18n

const notify = { showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn(), showConfirm: vi.fn(), showPrompt: vi.fn() }
vi.mock('../../../contexts', () => ({
  useNotification: () => notify,
  useInspector: () => ({ openEntity: vi.fn(), closeEntity: vi.fn(), setEntityData: vi.fn() }),
}))
vi.mock('../../../contexts/InspectorContext', () => ({
  useInspector: () => ({ openEntity: vi.fn(), closeEntity: vi.fn(), setEntityData: vi.fn() }),
}))
vi.mock('../../../hooks', () => ({
  usePermission: () => ({
    hasPermission: (p) => stable.perms.includes(p), canWrite: (r) => stable.perms.includes(`write:${r}`),
    canRead: (r) => stable.perms.includes(`read:${r}`), canDelete: () => false,
  }),
}))
const api = vi.hoisted(() => ({ generate: vi.fn(), getSchedule: vi.fn(), download: vi.fn() }))
const certs = vi.hoisted(() => ({ getStats: vi.fn() }))
vi.mock('../../../services', () => ({ reportsService: api, certificatesService: certs }))

import { InspectorObject } from '../../../components/inspector/InspectorObject'
import { setAppTimezone } from '../../../stores/timezoneStore'

const entry = (key, schedule) => ({ key: `report:${key}`, type: 'report', entityId: key, data: { key, schedule } })
const show = (e) => render(<MemoryRouter><InspectorObject entry={e} onTitle={() => {}} /></MemoryRouter>)
const WEEKLY = { enabled: true, frequency: 'weekly', time: '08:00', day_of_week: 0, recipients: ['pki@example.com'], format: 'csv' }

beforeEach(() => { vi.clearAllMocks(); setAppTimezone('UTC'); stable.perms = ['read:audit', 'export:audit', 'write:settings'] })

describe('ReportDetail in the inspector', () => {
  it('heads with the name and schedule state, the Report section first', () => {
    show(entry('expiring_certificates', WEEKLY))
    expect(screen.getByRole('heading', { level: 2, name: 'Certificats expirants' })).toBeInTheDocument()
    expect(screen.getAllByText('Planifié').length).toBeGreaterThan(0)
    expect(screen.getAllByRole('tab').map((t) => t.textContent)).toEqual(['Rapport', 'Exécutions', 'Aperçu'])
    expect(screen.getByRole('tab', { name: 'Rapport' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText('Hebdomadaire, le lundi, à 08:00')).toBeInTheDocument()
    expect(screen.getByText('pki@example.com')).toBeInTheDocument()
  })

  it('names its content as the queue does, not by its long description', () => {
    show(entry('expiring_certificates', WEEKLY))
    expect(screen.getByText('Contenu', { selector: 'dt' }).nextElementSibling).toHaveTextContent('Certificats expirants')
  })

  it('gives the current figure the certificate counters hold, with its sentence, for a reader of the certificates', async () => {
    stable.perms = [...stable.perms, 'read:certificates']
    certs.getStats.mockResolvedValue({ data: { expiring: 8 } })
    show(entry('expiring_certificates', WEEKLY))
    expect(await screen.findByText('8 certificats à J+30')).toBeInTheDocument()
    expect(screen.getByText('Même fenêtre que l’horizon à 30 jours de la vue d’ensemble, hors certificats révoqués.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Calculer' })).toBeNull()
    expect(api.generate).not.toHaveBeenCalled()
  })

  it('titles its « ⋯ » dialog and names the report in it', async () => {
    show(entry('expiring_certificates', WEEKLY))
    fireEvent.click(screen.getByTestId('inspector-more-actions'))
    const dialog = await screen.findByTestId('inspector-actions-dialog')
    expect(dialog).toHaveTextContent('Actions du rapport')
    expect(dialog).toHaveTextContent('Certificats expirants')
  })

  it('links to the certificates a report lists', () => {
    show(entry('expiring_certificates', WEEKLY))
    expect(screen.getByRole('link', { name: 'Voir ces certificats' })).toHaveAttribute('href', '/certificates?status=expiring')
  })

  it('computes the current figure on demand', async () => {
    api.generate.mockResolvedValue({ data: { content: JSON.stringify({ items: [{ id: 1 }, { id: 2 }], columns: ['id'] }), generated_at: '2026-11-18T10:00:00Z' } })
    show(entry('expiring_certificates', WEEKLY))
    fireEvent.click(screen.getByRole('button', { name: 'Calculer' }))
    await waitFor(() => expect(api.generate).toHaveBeenCalledWith('expiring_certificates', { format: 'json', days: 30 }))
    expect(await screen.findByText('2 lignes')).toBeInTheDocument()
  })

  it('says the server serves no run history', () => {
    const { container } = show(entry('audit_summary', WEEKLY))
    fireEvent.click(screen.getByRole('tab', { name: 'Exécutions' }))
    expect(container).toHaveTextContent('ne fournit pas d’historique des exécutions')
  })

  it('previews the rows of the report', async () => {
    api.generate.mockResolvedValue({ data: { content: JSON.stringify({ items: [{ id: 1, common_name: 'a.example.com' }], columns: ['id', 'common_name'] }) } })
    show(entry('certificate_inventory', WEEKLY))
    fireEvent.click(screen.getByRole('tab', { name: 'Aperçu' }))
    fireEvent.click(screen.getByRole('button', { name: 'Générer' }))
    expect(await screen.findByText('a.example.com')).toBeInTheDocument()
  })

  it('offers neither download nor computation without export:audit', () => {
    stable.perms = ['read:audit']
    show(entry('expiring_certificates', WEEKLY))
    expect(screen.queryByRole('button', { name: 'Télécharger' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Calculer' })).toBeDisabled()
    expect(screen.queryByTestId('inspector-more-actions')).toBeNull()
  })
})
