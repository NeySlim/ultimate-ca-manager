/**
 * A report in the module dock: heading, the Report, Runs and Preview sections, the
 * certificates it lists, its actions by right behind « ⋯ ».
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useState } from 'react'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
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
const api = vi.hoisted(() => ({ generate: vi.fn(), getSchedule: vi.fn(), download: vi.fn(), updateSchedule: vi.fn() }))
const certs = vi.hoisted(() => ({ getStats: vi.fn() }))
vi.mock('../../../services', () => ({ reportsService: api, certificatesService: certs }))

import { ReportDock } from '../ReportDetail'
import { useReportActions } from '../useReportActions'
import { setAppTimezone } from '../../../stores/timezoneStore'

function Harness({ e }) {
  const [section, setSection] = useState('report')
  const actions = useReportActions({ schedules: { [e.key]: e.schedule } })
  return <div className="atl"><ReportDock entry={e} section={section} onSection={setSection} onClose={() => {}} actions={actions} />{actions.dialog}</div>
}
const entry = (key, schedule) => ({ key, schedule })
const show = (e) => render(<MemoryRouter><Harness e={e} /></MemoryRouter>)
const more = () => screen.getByRole('button', { name: /^Autres actions pour/ })
const WEEKLY = { enabled: true, frequency: 'weekly', time: '08:00', day_of_week: 0, recipients: ['pki@example.com'], format: 'csv' }

beforeEach(() => { vi.clearAllMocks(); setAppTimezone('UTC'); stable.perms = ['read:audit', 'export:audit', 'write:settings'] })

describe('ReportDock', () => {
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
    fireEvent.click(more())
    const dialog = await screen.findByTestId('report-menu-dialog')
    expect(dialog).toHaveTextContent('Actions du rapport')
    expect(dialog).toHaveTextContent('Certificats expirants')
  })

  it('titles the test dialog as its button, in the mockup\'s words', async () => {
    show(entry('expiring_certificates', WEEKLY))
    fireEvent.click(more())
    fireEvent.click(await screen.findByRole('button', { name: 'Envoyer un test…' }))
    const dialog = await screen.findByRole('dialog', { name: 'Envoyer un test' })
    expect(dialog).toHaveTextContent('Envoyer un rapport test « Certificats expirants » pour vérifier la livraison par e-mail.')
    expect(within(dialog).getByLabelText('E-mail du destinataire')).toBeInTheDocument()
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

  describe('schedule dialog, in the timezone the row reads', () => {
    const MONTHLY = { enabled: true, frequency: 'monthly', time: '06:45', day_of_month: 1, recipients: ['direction-si@example.com'], format: 'csv' }
    // Friday 20 November 2026, 10:00 UTC: the next runs fall in winter time, Paris at UTC+1
    beforeEach(() => { vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date(Date.UTC(2026, 10, 20, 10))); setAppTimezone('Europe/Paris') })
    afterEach(() => { vi.useRealTimers() })
    const openEdit = async () => {
      fireEvent.click(more())
      fireEvent.click(await screen.findByRole('button', { name: 'Modifier la planification…' }))
      return screen.findByTestId('schedule-form')
    }

    it('shows the hour of the row, saves it back in UTC', async () => {
      api.updateSchedule.mockResolvedValue({ data: {} })
      show(entry('audit_summary', MONTHLY))
      expect(screen.getByText('Mensuel, le 1er, à 07:45')).toBeInTheDocument()
      const form = await openEdit()
      expect(within(form).getByLabelText('Heure d’envoi')).toHaveValue('07:45')
      expect(within(form).getByText('Format HH:MM.')).toBeInTheDocument()
      fireEvent.click(within(form).getByRole('button', { name: 'Planifier' }))
      await waitFor(() => expect(api.updateSchedule).toHaveBeenCalledWith({ audit_summary: expect.objectContaining({ time: '06:45', day_of_month: 1 }) }))
    })

    it('converts a typed hour and day to the scheduler\'s UTC, moving a weekly day when it has to', async () => {
      api.updateSchedule.mockResolvedValue({ data: {} })
      show(entry('audit_summary', { ...MONTHLY, frequency: 'weekly', time: '08:00', day_of_week: 0 }))
      const form = await openEdit()
      expect(within(form).getByLabelText('Heure d’envoi')).toHaveValue('09:00')
      fireEvent.change(within(form).getByLabelText('Heure d’envoi'), { target: { value: '00:30' } })
      fireEvent.click(within(form).getByRole('button', { name: 'Planifier' }))
      // Monday 00:30 in Paris is Sunday 23:30 UTC
      await waitFor(() => expect(api.updateSchedule).toHaveBeenCalledWith({ audit_summary: expect.objectContaining({ time: '23:30', day_of_week: 6 }) }))
    })

    it('keeps UTC on both sides, said, when the conversion moves a weekly day', async () => {
      show(entry('audit_summary', { ...MONTHLY, frequency: 'weekly', time: '23:30', day_of_week: 6 }))
      expect(screen.getByText('Hebdomadaire, le dimanche, à 23:30 UTC')).toBeInTheDocument()
      const form = await openEdit()
      expect(within(form).getByLabelText('Heure d’envoi (UTC)')).toHaveValue('23:30')
      expect(within(form).getByLabelText('Jour de la semaine')).toHaveValue('6')
      expect(within(form).getByText('Format HH:MM, en heure UTC comme le planificateur.')).toBeInTheDocument()
    })

    it('refuses a monthly hour the conversion would move out of the days of the month', async () => {
      show(entry('audit_summary', MONTHLY))
      const form = await openEdit()
      fireEvent.change(within(form).getByLabelText('Heure d’envoi'), { target: { value: '00:30' } })
      fireEvent.click(within(form).getByRole('button', { name: 'Planifier' }))
      expect(await within(form).findByText(/un autre jour du mois en UTC/)).toBeInTheDocument()
      expect(api.updateSchedule).not.toHaveBeenCalled()
    })
  })

  it('offers neither download nor computation without export:audit', () => {
    stable.perms = ['read:audit']
    show(entry('expiring_certificates', WEEKLY))
    expect(screen.queryByRole('button', { name: 'Télécharger' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Calculer' })).toBeDisabled()
    expect(screen.queryByRole('button', { name: /^Autres actions pour/ })).toBeNull()
  })
})
