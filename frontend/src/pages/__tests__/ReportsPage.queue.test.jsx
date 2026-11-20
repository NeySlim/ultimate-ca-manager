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
vi.mock('../../services', () => ({ reportsService: api }))

import ReportsPage from '../ReportsPage'

const ALL = ['read:audit', 'export:audit', 'write:settings']
const HOUR = 3600000
const hhmm = (d) => `${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}`
const renderPage = () => render(<MemoryRouter><ReportsPage /></MemoryRouter>)
const group = (name) => screen.getByRole('heading', { level: 2, name: new RegExp(`^${name}`) }).closest('section')

beforeEach(() => {
  vi.clearAllMocks()
  stable.perms = ALL
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
    renderPage()
    expect(await screen.findByText('2 rapports planifiés')).toBeInTheDocument()
    expect(screen.getByText('Inventaires et échéances planifiés.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Planifier un rapport' })).toHaveClass('is-primary')
  })

  it('groups the scheduled reports by next run; the frequency is the pill', async () => {
    renderPage()
    await screen.findByText('Certificats expirants')
    const today = group('Prochaine exécution sous 24 h')
    const li = within(today).getByText('Certificats expirants').closest('li')
    expect(within(li).getByText(/^Quotidien · \d\d:\d\d UTC$/)).toHaveClass('wk-kind')
    expect(within(li).getByText('CSV · pki@example.com')).toBeInTheDocument()
    expect(within(li).getByText('dans 3 h')).toBeInTheDocument()
    expect(within(group('Planifiés')).getByText('JSON · Aucun destinataire')).toBeInTheDocument()
  })

  it('folds the reports without a schedule, each downloadable and schedulable', async () => {
    renderPage()
    const toggle = await screen.findByRole('button', { name: /^Non planifiés/ })
    expect(toggle).toHaveTextContent('Non planifiés9')
    fireEvent.click(toggle)
    expect(screen.getByRole('button', { name: 'Planifier Résumé d\'audit' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Télécharger Résumé d\'audit' }))
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
    expect(await within(dialog).findByText(/au moins un destinataire/)).toBeInTheDocument()
    expect(api.updateSchedule).not.toHaveBeenCalled()
    fireEvent.change(within(dialog).getByLabelText('Destinataires'), { target: { value: 'a@example.com, b@example.com' } })
    fireEvent.change(within(dialog).getByLabelText('Heure d\'envoi (UTC)'), { target: { value: '07:00' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Planifier' }))
    await waitFor(() => expect(api.updateSchedule).toHaveBeenCalledWith({ ca_hierarchy: expect.objectContaining({
      enabled: true, frequency: 'weekly', time: '07:00', recipients: ['a@example.com', 'b@example.com'], format: 'csv',
    }) }))
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
    fireEvent.click(await screen.findByRole('button', { name: 'Composer un PDF…' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByLabelText('Certificats expirants'))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Générer le PDF' }))
    await waitFor(() => expect(api.generateCustomPDF).toHaveBeenCalledWith({ sections: ['expiry'] }))
  })

  it('offers no action to a reader of the audit log', async () => {
    stable.perms = ['read:audit']
    renderPage()
    await screen.findByText('Certificats expirants')
    expect(screen.queryByRole('button', { name: /Télécharger|Planifier|Composer/ })).toBeNull()
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0)
  })

  it('opens a report in the inspector from its name', async () => {
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Certificats expirants' }))
    expect(openEntity).toHaveBeenCalledWith('report', 'expiring_certificates', { data: expect.objectContaining({ key: 'expiring_certificates' }) })
  })

  it('shows a load failure with Retry', async () => {
    api.getSchedule.mockRejectedValueOnce(new Error('HTTP 500'))
    renderPage()
    const alert = await screen.findByRole('alert')
    fireEvent.click(within(alert).getByRole('button', { name: 'Réessayer' }))
    expect(await screen.findByText('Certificats expirants')).toBeInTheDocument()
  })
})
