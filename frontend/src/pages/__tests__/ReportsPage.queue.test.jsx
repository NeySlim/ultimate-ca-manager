/**
 * ReportsPage as a work queue: scheduled reports grouped by next run, the others
 * folded below; downloads, scheduling, suspension and the custom PDF are each
 * offered only with their right.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within, configure } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

configure({ asyncUtilTimeout: 5000 })

const stable = vi.hoisted(() => ({
  i18n: null, perms: [],
  notify: { showSuccess: () => {}, showError: () => {}, showInfo: () => {}, showWarning: () => {} },
}))
vi.mock('react-i18next', () => ({ useTranslation: () => stable.i18n, Trans: ({ children }) => children, initReactI18next: { type: '3rdParty', init: () => {} } }))
import { frI18n } from '../../components/work/__tests__/frI18n'
stable.i18n = frI18n

const openEntity = vi.fn()
vi.mock('../../contexts', () => ({
  useNotification: () => stable.notify,
  useMobile: () => ({ isMobile: false, isTablet: false, screenWidth: 1600, sidebarOpen: true, setSidebarOpen: () => {} }),
  useInspector: () => ({ openEntity, activeKey: null }),
}))
vi.mock('../../hooks', () => ({
  usePermission: () => ({
    hasPermission: (p) => stable.perms.includes(p), canWrite: (r) => stable.perms.includes(`write:${r}`),
    canRead: (r) => stable.perms.includes(`read:${r}`), canDelete: () => false,
  }),
}))
const api = vi.hoisted(() => ({
  getSchedule: vi.fn(), getPdfTemplates: vi.fn(), updateSchedule: vi.fn(), download: vi.fn(), generateCustomPDF: vi.fn(), sendTest: vi.fn(), generate: vi.fn(),
}))
const certs = vi.hoisted(() => ({ getStats: vi.fn() }))
vi.mock('../../services', () => ({ reportsService: api, certificatesService: certs }))

import { renderAtUrl } from '../../test/dockUrl'
import ReportsPage from '../ReportsPage'
import { setAppTimezone } from '../../stores/timezoneStore'

const ALL = ['read:audit', 'export:audit', 'write:settings']
const HOUR = 3600000
const hhmm = (d) => `${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}`
const renderPage = () => render(<MemoryRouter><ReportsPage /></MemoryRouter>)
const group = (name) => screen.getByRole('heading', { level: 2, name: new RegExp(`^${name}`) }).closest('section')

beforeEach(() => {
  vi.clearAllMocks()
  setAppTimezone('UTC')
  stable.perms = ALL
  certs.getStats.mockResolvedValue({ data: { total: 282, expiring: 8, expired: 3, revoked: 4 } })
  const soon = new Date(Date.now() + 3 * HOUR)
  api.getSchedule.mockResolvedValue({ data: {
    expiring_certificates: { enabled: true, frequency: 'daily', time: hhmm(soon), recipients: ['pki@example.com'], format: 'csv' },
    certificate_inventory: { enabled: true, frequency: 'monthly', time: '06:45', day_of_month: 28, recipients: [], format: 'json' },
  } })
  api.getPdfTemplates.mockResolvedValue({ data: { templates: {}, sections: ['executive_summary', 'expiry'] } })
  api.updateSchedule.mockResolvedValue({ data: {} })
  api.download.mockResolvedValue('a,b\n')
  URL.createObjectURL = vi.fn(() => 'blob:x'); URL.revokeObjectURL = vi.fn()
})

describe('ReportsPage queue', () => {
  it('heads the page with the scheduled count, the intent and Schedule a report', async () => {
    const { container } = renderPage()
    expect(await screen.findByText('2 rapports planifiés')).toBeInTheDocument()
    expect(screen.getByText('Cochez plusieurs rapports pour les télécharger ensemble ; les chiffres suivent l’inventaire, comme la vue d’ensemble.')).toBeInTheDocument()
    expect(container.querySelector('.page-head .actions #report-pdf')).toHaveTextContent('Composer un PDF…')
    // The mockup's phone head keeps the primary button only: the composer is in the head's « ⋯ » menu, as the journal's actions
    expect(container.querySelector('.page-head .page-more [data-more="report-pdf"]')).toHaveTextContent('Composer un PDF…')
    expect(container.querySelector('.work-view > .phone-only')).toBeNull()
    expect(screen.getByText('Inventaires et échéances planifiés.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Planifier un rapport' })).toHaveClass('btn', 'primary')
  })

  it('groups the scheduled reports by next run; the frequency is the pill', async () => {
    renderPage()
    await screen.findByText('Certificats expirants')
    const today = group('Prochaine exécution sous 24 h')
    const li = within(today).getByText('Certificats expirants').closest('li')
    expect(within(li).getByText(/^Quotidien · \d\d:\d\d$/)).toHaveClass('queue-kind')
    expect(within(li).getByText('CSV · pki@example.com')).toBeInTheDocument()
    expect(within(li).getByText('dans 3 h')).toBeInTheDocument()
    expect(within(group('Planifiés')).getByText('JSON · Aucun destinataire')).toBeInTheDocument()
  })

  it('gives the figure the certificate counters hold, as the mockup, for a reader of the certificates', async () => {
    stable.perms = [...ALL, 'read:certificates']
    renderPage()
    const li = (await screen.findByText('8 certificats à J+30 · pki@example.com')).closest('li')
    expect(within(li).getByText('Certificats expirants')).toBeInTheDocument()
    // The inventory has no counter of its own: its format stays
    expect(within(group('Planifiés')).getByText('JSON · Aucun destinataire')).toBeInTheDocument()
  })

  it('reads the hour of a schedule in the user\'s timezone, without a UTC suffix', async () => {
    setAppTimezone('Asia/Tokyo')
    renderPage()
    await screen.findByText('Certificats expirants')
    // 06:45 UTC on the 28th is 15:45 the same day in Tokyo
    expect(within(group('Planifiés')).getByText('Mensuel · 15:45')).toHaveClass('queue-kind')
  })

  it('folds the reports without a schedule, each downloadable and schedulable', async () => {
    renderPage()
    const toggle = await screen.findByRole('button', { name: /^Non planifiés/ })
    expect(toggle).toHaveTextContent('Non planifiés9')
    // a catalog of kinds, laid two abreast on a wide screen (adjust.css)
    expect(toggle.closest('.work-history')).toHaveClass('catalog')
    fireEvent.click(toggle)
    expect(screen.getByRole('button', { name: 'Planifier Résumé d’audit' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Télécharger Résumé d’audit' }))
    await waitFor(() => expect(api.download).toHaveBeenCalledWith('audit_summary', 'csv', 30))
  })

  it('downloads a report in its schedule format', async () => {
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Télécharger Inventaire des certificats' }))
    await waitFor(() => expect(api.download).toHaveBeenCalledWith('certificate_inventory', 'json', 30))
  })

  it('schedules a report: refuses a schedule without recipient, then sends it enabled', async () => {
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Planifier un rapport' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByLabelText('Contenu')).toHaveValue('ca_hierarchy')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Planifier' }))
    expect(await within(dialog).findByText('Saisissez au moins une adresse.')).toBeInTheDocument()
    expect(api.updateSchedule).not.toHaveBeenCalled()
    fireEvent.change(within(dialog).getByLabelText('Destinataires'), { target: { value: 'a@example.com, b@example.com' } })
    fireEvent.change(within(dialog).getByLabelText('Heure d’envoi'), { target: { value: '25:00' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Planifier' }))
    expect(await within(dialog).findByText('Heure invalide : format HH:MM, de 00:00 à 23:59.')).toBeInTheDocument()
    expect(within(dialog).getByLabelText('Heure d’envoi')).toHaveFocus()
    fireEvent.change(within(dialog).getByLabelText('Heure d’envoi'), { target: { value: '07:00' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Planifier' }))
    await waitFor(() => expect(api.updateSchedule).toHaveBeenCalledWith({ ca_hierarchy: expect.objectContaining({
      enabled: true, frequency: 'weekly', time: '07:00', recipients: ['a@example.com', 'b@example.com'], format: 'csv',
    }) }))
  })

  it('gives the format the whole line when no day field stands beside it', async () => {
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Planifier un rapport' }))
    const dialog = await screen.findByRole('dialog')
    const format = () => dialog.querySelector('#sch-format').closest('.field')
    expect(format()).not.toHaveClass('full')
    fireEvent.change(dialog.querySelector('#sch-freq'), { target: { value: 'daily' } })
    expect(format()).toHaveClass('full')
  })

  it('gives the focus back to Schedule a report when its dialog is left with Escape', async () => {
    renderPage()
    const button = await screen.findByRole('button', { name: 'Planifier un rapport' })
    button.focus()
    fireEvent.click(button)
    const dialog = await screen.findByRole('dialog')
    fireEvent.keyDown(dialog, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await waitFor(() => expect(button).toHaveFocus())
  })

  it('suspends several schedules in one update', async () => {
    renderPage()
    await screen.findByText('Certificats expirants')
    fireEvent.click(screen.getByRole('checkbox', { name: 'Tout sélectionner : Prochaine exécution sous 24 h' }))
    fireEvent.click(screen.getByRole('checkbox', { name: 'Tout sélectionner : Planifiés' }))
    fireEvent.click(within(screen.getByRole('group', { name: 'Actions groupées' })).getByRole('button', { name: 'Suspendre la planification' }))
    await waitFor(() => expect(api.updateSchedule).toHaveBeenCalledTimes(1))
    const body = api.updateSchedule.mock.calls[0][0]
    expect(Object.keys(body).sort()).toEqual(['certificate_inventory', 'expiring_certificates'])
    expect(Object.values(body).every((s) => s.enabled === false)).toBe(true)
  })

  it('builds a PDF from the sections chosen', async () => {
    api.generateCustomPDF.mockResolvedValue(new Blob(['%PDF']))
    renderPage()
    fireEvent.click((await screen.findAllByRole('button', { name: 'Composer un PDF…' }))[0])
    const dialog = await screen.findByRole('dialog')
    // One sentence says what the dialog does: its subtitle
    expect(dialog).toHaveTextContent('Les sections choisies, téléchargées en un seul PDF.')
    expect(dialog).not.toHaveTextContent('Sélectionnez les sections')
    fireEvent.click(within(dialog).getByLabelText('Certificats expirants'))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Générer le PDF' }))
    await waitFor(() => expect(api.generateCustomPDF).toHaveBeenCalledWith({ sections: ['expiry'] }))
  })

  // Ticking all or none acts on the list: small buttons above it, the foot keeps Annuler and Générer
  it('puts the select-all and select-none above the sections, the foot keeping its two buttons', async () => {
    renderPage()
    fireEvent.click((await screen.findAllByRole('button', { name: 'Composer un PDF…' }))[0])
    const dialog = await screen.findByRole('dialog')
    const row = dialog.querySelector('.pdf-select')
    expect(row.nextElementSibling).toHaveClass('columns-list')
    expect([...row.querySelectorAll('button')].map((b) => b.textContent)).toEqual(['Tout sélectionner', 'Tout désélectionner'])
    expect([...dialog.querySelectorAll('.modal-actions .btn')].map((b) => b.textContent)).toEqual(['Annuler', 'Générer le PDF'])
    fireEvent.click(within(row).getByRole('button', { name: 'Tout sélectionner' }))
    expect(within(dialog).getByLabelText('Certificats expirants')).toBeChecked()
  })

  it('offers no action to a reader of the audit log', async () => {
    stable.perms = ['read:audit']
    renderPage()
    await screen.findByText('Certificats expirants')
    expect(screen.queryByRole('button', { name: /Télécharger|Planifier|Composer/ })).toBeNull()
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0)
  })

  it('opens a report in the module dock from its name, its tabs those of the mockup then Aperçu', async () => {
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Certificats expirants' }))
    const dock = await screen.findByRole('complementary', { name: 'Détail : Rapports' })
    expect(within(dock).getByRole('heading', { level: 2, name: 'Certificats expirants' })).toBeInTheDocument()
    expect(within(dock).getAllByRole('tab').map((tab) => tab.textContent)).toEqual(['Rapport', 'Exécutions', 'Aperçu'])
    expect(openEntity).not.toHaveBeenCalled()
  })

  it('shows a load failure with Retry', async () => {
    api.getSchedule.mockRejectedValueOnce(new Error('HTTP 500'))
    renderPage()
    const alert = await screen.findByRole('alert')
    fireEvent.click(within(alert).getByRole('button', { name: 'Réessayer' }))
    expect(await screen.findByText('Certificats expirants')).toBeInTheDocument()
  })
})

describe('the report dock in the URL', () => {
  it('reopens the report and section of the URL, writes the one opened, drops an unknown one', async () => {
    const r = renderAtUrl(<ReportsPage />, '/reports?item=expiring_certificates&section=runs')
    const dock = await screen.findByRole('complementary', { name: 'Détail : Rapports' })
    expect(within(dock).getByRole('heading', { level: 2, name: 'Certificats expirants' })).toBeInTheDocument()
    expect(within(dock).getByRole('tab', { name: 'Exécutions' })).toHaveAttribute('aria-selected', 'true')
    fireEvent.click(within(dock).getByRole('tab', { name: 'Aperçu' }))
    expect(r.where()).toBe('/reports?item=expiring_certificates&section=preview')
    r.unmount()
    const gone = renderAtUrl(<ReportsPage />, '/reports?item=nope')
    await waitFor(() => expect(gone.where()).toBe('/reports'))
  })
})
