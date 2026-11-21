/**
 * Settings page on the sectioned template: every section on the page, a change counted
 * in the save bar and marked in the table of contents, undo back to what was loaded,
 * one save through today's routes, a failed route named on its section while the others
 * are stored and its input kept, a link to ?tab= landing on its frame, and leaving with
 * changes pending: no question, the draft found again on the return.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Link, Routes, Route } from 'react-router-dom'

vi.mock('../settings/GeneralSection', () => ({
  default: ({ settings, updateSetting }) => (
    <label>
      name
      <input aria-label="system-name" value={settings.system_name || ''} onChange={(e) => updateSetting('system_name', e.target.value)} />
    </label>
  ),
}))
vi.mock('../settings/EmailSection', () => ({
  default: ({ settings, updateSetting, fieldErrors = {} }) => (
    <>
      <input aria-label="smtp-host" value={settings.smtp_host || ''} onChange={(e) => updateSetting('smtp_host', e.target.value)} />
      <input aria-label="smtp-port" value={settings.smtp_port ?? ''} aria-invalid={fieldErrors.smtp_port ? true : undefined}
        onChange={(e) => updateSetting('smtp_port', e.target.value === '' ? '' : Number(e.target.value))} />
      {fieldErrors.smtp_port && <p>{fieldErrors.smtp_port}</p>}
    </>
  ),
}))
vi.mock('../settings/AuditSection', () => ({
  default: ({ syslogConfig, updateSyslogConfig, updateSetting, settings, handleTestSyslog, syslogTestResult }) => (
    <>
      <button type="button" onClick={handleTestSyslog}>test-syslog</button>
      {syslogTestResult && <p data-testid="syslog-result">{`${syslogTestResult.ok}:${syslogTestResult.text}`}</p>}
      <input aria-label="syslog-host" value={syslogConfig.host || ''} onChange={(e) => updateSyslogConfig('host', e.target.value)} />
      <input aria-label="retention" value={settings.audit_retention_days ?? ''} onChange={(e) => updateSetting('audit_retention_days', e.target.value)} />
    </>
  ),
}))

vi.mock('../../hooks/usePermission', () => ({
  usePermission: () => ({
    hasPermission: () => true, canRead: () => true, canWrite: () => true, canDelete: () => true,
    isAdmin: () => true, permissions: ['*'],
  }),
}))

import { notificationSpies } from './pageRenderingSetup.jsx'

import SettingsPage from '../SettingsPage'
import { settingsService } from '../../services/settings.service'
import { auditService } from '../../services'
import { dropAllDrafts } from '../../components/sectioned/draftMemory'

const renderPage = (entry = '/settings') => render(
  <MemoryRouter initialEntries={[entry]}>
    <Link to="/certificates">elsewhere</Link>
    <SettingsPage />
  </MemoryRouter>,
)

const bar = () => document.getElementById('settings-savebar')
const saveButton = () => within(bar()).getByRole('button', { name: 'common.save' })
const undoButton = () => within(bar()).getByRole('button', { name: 'sectioned.undo' })
const tocLink = (label) => within(screen.getByRole('navigation', { name: 'settings.tocLabel' })).getByRole('link', { name: new RegExp(label) })

beforeEach(() => {
  settingsService.getAll = vi.fn().mockResolvedValue({ data: { system_name: 'PKI', audit_retention_days: 90 } })
  settingsService.getEmailSettings = vi.fn().mockResolvedValue({ data: { smtp_host: 'smtp.example.com', smtp_port: 587 } })
  settingsService.getSyslogConfig = vi.fn().mockResolvedValue({ data: { enabled: true, host: 'log.example.com', port: 514 } })
  settingsService.updateBulk = vi.fn().mockResolvedValue({ data: {} })
  settingsService.updateEmailSettings = vi.fn().mockResolvedValue({ data: {} })
  settingsService.updateSyslogConfig = vi.fn().mockResolvedValue({ data: {} })
  notificationSpies.showConfirm = vi.fn().mockResolvedValue(false)
  window.history.replaceState(null, '', '/settings')
})
afterEach(() => { vi.clearAllMocks(); dropAllDrafts() })

async function loaded(entry) {
  renderPage(entry)
  await screen.findByLabelText('system-name')
  await waitFor(() => expect(screen.getByLabelText('syslog-host')).toHaveValue('log.example.com'))
}

// The whole page is mounted with its 19 sections: a loaded machine takes seconds per test
describe('SettingsPage: one page, one save bar', { timeout: 20000 }, () => {
  it('lands a link to ?tab= on its frame title without the keyboard outline', async () => {
    Element.prototype.scrollIntoView = vi.fn()
    await loaded('/settings?tab=email')
    const title = document.getElementById('set-title-email')
    await waitFor(() => expect(document.activeElement).toBe(title))
    expect(title).toHaveAttribute('data-quiet-focus')
    delete Element.prototype.scrollIntoView
  })

  it('shows every section in a frame of its own, listed by group', async () => {
    await loaded()
    for (const id of ['general', 'email', 'audit', 'security', 'backup', 'about']) {
      expect(document.getElementById(`set-sec-${id}`)).toBeInTheDocument()
    }
    expect(screen.getByLabelText('smtp-host')).toBeInTheDocument()
    expect(tocLink('settings.tabs.email')).toHaveAttribute('href', '/settings?tab=email')
    expect(saveButton()).toBeDisabled()
  })

  it('counts a change, marks its section, and undo brings back what was loaded', async () => {
    await loaded()
    fireEvent.change(screen.getByLabelText('system-name'), { target: { value: 'PKI 2' } })
    fireEvent.change(screen.getByLabelText('syslog-host'), { target: { value: 'log2.example.com' } })
    expect(bar()).toHaveTextContent('sectioned.pendingTitle')
    expect(tocLink('settings.tabs.general')).toHaveTextContent('sectioned.flagModified')
    expect(tocLink('settings.tabs.audit')).toHaveTextContent('sectioned.flagModified')
    expect(tocLink('settings.tabs.email')).not.toHaveTextContent('sectioned.flagModified')
    fireEvent.click(undoButton())
    expect(screen.getByLabelText('system-name')).toHaveValue('PKI')
    expect(screen.getByLabelText('syslog-host')).toHaveValue('log.example.com')
    expect(saveButton()).toBeDisabled()
  })

  it('stores each changed part by its own route, once', async () => {
    await loaded()
    fireEvent.change(screen.getByLabelText('system-name'), { target: { value: 'PKI 2' } })
    fireEvent.change(screen.getByLabelText('retention'), { target: { value: '30' } })
    fireEvent.change(screen.getByLabelText('syslog-host'), { target: { value: 'log2.example.com' } })
    await act(async () => { fireEvent.click(saveButton()) })
    expect(settingsService.updateBulk).toHaveBeenCalledTimes(1)
    expect(settingsService.updateBulk.mock.calls[0][0]).toMatchObject({ system_name: 'PKI 2', audit_retention_days: '30' })
    expect(settingsService.updateSyslogConfig).toHaveBeenCalledWith(expect.objectContaining({ host: 'log2.example.com' }))
    expect(settingsService.updateEmailSettings).not.toHaveBeenCalled()
    expect(notificationSpies.showSuccess).toHaveBeenCalledWith('sectioned.savedToast')
  })

  it('names the section whose route failed, stores the others and keeps the input', async () => {
    await loaded()
    settingsService.updateEmailSettings = vi.fn().mockRejectedValue(new Error('SMTP refused'))
    // What the server holds after the save: the stored name, the old SMTP host
    settingsService.getAll = vi.fn().mockResolvedValue({ data: { system_name: 'PKI 2', audit_retention_days: 90 } })
    fireEvent.change(screen.getByLabelText('system-name'), { target: { value: 'PKI 2' } })
    fireEvent.change(screen.getByLabelText('smtp-host'), { target: { value: 'smtp2.example.com' } })
    await act(async () => { fireEvent.click(saveButton()) })
    await waitFor(() => expect(settingsService.getAll).toHaveBeenCalled())
    expect(settingsService.updateBulk).toHaveBeenCalledTimes(1)
    const email = document.getElementById('set-sec-email')
    expect(within(email).getByRole('alert')).toHaveTextContent('SMTP refused')
    expect(within(document.getElementById('set-sec-general')).queryByRole('alert')).toBeNull()
    expect(screen.getByLabelText('smtp-host')).toHaveValue('smtp2.example.com')
    expect(tocLink('settings.tabs.email')).toHaveTextContent('sectioned.flagError')
    expect(bar()).toHaveTextContent('sectioned.saveFailedTitle')
    expect(notificationSpies.showError).toHaveBeenCalledWith('sectioned.saveFailedToast')
  })

  it('sends nothing while a port is out of range, marks the field and focuses it', async () => {
    await loaded()
    fireEvent.change(screen.getByLabelText('smtp-port'), { target: { value: '99999' } })
    fireEvent.change(screen.getByLabelText('system-name'), { target: { value: 'PKI 2' } })
    await act(async () => { fireEvent.click(saveButton()) })
    expect(settingsService.updateEmailSettings).not.toHaveBeenCalled()
    expect(settingsService.updateBulk).not.toHaveBeenCalled()
    const port = screen.getByLabelText('smtp-port')
    expect(port).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByText('settings.portOutOfRange')).toBeInTheDocument()
    expect(document.activeElement).toBe(port)
    expect(tocLink('settings.tabs.email')).toHaveTextContent('sectioned.flagError')
    expect(screen.getByRole('status')).toHaveTextContent('sectioned.fieldsToCorrect')
    // Typing in the field clears its mark; a valid port is then sent
    fireEvent.change(port, { target: { value: '2525' } })
    expect(port).not.toHaveAttribute('aria-invalid')
    await act(async () => { fireEvent.click(saveButton()) })
    expect(settingsService.updateEmailSettings).toHaveBeenCalledWith(expect.objectContaining({ smtp_port: 2525 }))
  })

  it('dates the last save from a real save only, not from a renewal run in the same log', async () => {
    auditService.getLogs = vi.fn().mockResolvedValue({ data: [
      { id: 3, action: 'auto_renewal_manual_run', resource_name: 'Auto-Renewal', details: 'Manual run: 0 renewed', username: 'bob', timestamp: '2026-11-19T10:00:00Z' },
      { id: 2, action: 'settings_update', resource_name: 'General Settings', details: 'Updated general settings', username: 'alice', timestamp: '2026-11-18T09:00:00Z' },
    ] })
    await loaded()
    await waitFor(() => expect(bar()).toHaveTextContent('sectioned.lastSavedBy'))
    const history = screen.getByRole('region', { name: 'settings.historyTitle' })
    expect(within(history).getByText('settings.history.general')).toBeInTheDocument()
    expect(within(history).queryByText('Auto-Renewal')).toBeNull()
  })

  it('says only that nothing is pending when the log holds no save', async () => {
    auditService.getLogs = vi.fn().mockResolvedValue({ data: [
      { id: 3, action: 'auto_renewal_manual_run', resource_name: 'Auto-Renewal', username: 'bob', timestamp: '2026-11-19T10:00:00Z' },
    ] })
    await loaded()
    await waitFor(() => expect(auditService.getLogs).toHaveBeenCalled())
    await waitFor(() => expect(screen.getByRole('region', { name: 'settings.historyTitle' })).toBeInTheDocument())
    expect(bar()).toHaveTextContent('sectioned.nothingPending')
    expect(bar()).not.toHaveTextContent('sectioned.lastSaved')
  })

  it('saves on Enter in a field, as a form does', async () => {
    await loaded()
    const name = screen.getByLabelText('system-name')
    fireEvent.change(name, { target: { value: 'PKI 2' } })
    await act(async () => { fireEvent.keyDown(name, { key: 'Enter' }) })
    expect(settingsService.updateBulk).toHaveBeenCalledWith(expect.objectContaining({ system_name: 'PKI 2' }))
  })

  it('tests the saved syslog forwarding and keeps the result beside the button', async () => {
    settingsService.testSyslog = vi.fn().mockResolvedValue({ message: 'sent' })
    await loaded()
    await act(async () => { fireEvent.click(screen.getByText('test-syslog')) })
    expect(settingsService.testSyslog).toHaveBeenCalledTimes(1)
    expect(screen.getByTestId('syslog-result')).toHaveTextContent('true:sent')
  })

  it('says syslog is off instead of testing a forwarding that is not saved on', async () => {
    settingsService.getSyslogConfig = vi.fn().mockResolvedValue({ data: { enabled: false, host: 'log.example.com', port: 514 } })
    settingsService.testSyslog = vi.fn()
    await loaded()
    await act(async () => { fireEvent.click(screen.getByText('test-syslog')) })
    expect(settingsService.testSyslog).not.toHaveBeenCalled()
    expect(screen.getByTestId('syslog-result')).toHaveTextContent('false:settings.syslogTestOff')
  })

  it('lands a link to ?tab= on the frame of that section', async () => {
    const scrolled = []
    Element.prototype.scrollIntoView = vi.fn(function scroll() { scrolled.push(this.id) })
    await loaded('/settings?tab=email')
    await waitFor(() => expect(scrolled).toContain('set-sec-email'))
    expect(document.activeElement).toBe(document.getElementById('set-title-email'))
    delete Element.prototype.scrollIntoView
  })

  it('lands a link to ?section= as one to ?tab=', async () => {
    const scrolled = []
    Element.prototype.scrollIntoView = vi.fn(function scroll() { scrolled.push(this.id) })
    await loaded('/settings?section=audit')
    await waitFor(() => expect(scrolled).toContain('set-sec-audit'))
    expect(document.activeElement).toBe(document.getElementById('set-title-audit'))
    expect(tocLink('settings.tabs.audit')).toHaveAttribute('aria-current', 'true')
    delete Element.prototype.scrollIntoView
  })

  it('draws every section with the mockup rules, in no outer form', async () => {
    await loaded()
    const body = (id) => document.querySelector(`#set-sec-${id} > .settings-body`)
    for (const id of ['general', 'security', 'email', 'https', 'appearance', 'backup', 'audit', 'database', 'updates', 'scheduler', 'autoRenewal', 'about', 'sso', 'adConnector', 'microsoftCA', 'xcepWstep', 'webhooks', 'deploy', 'ct']) expect(body(id), id).not.toHaveClass('atl-out')
    expect(document.getElementById('settings-form').tagName).toBe('DIV')
    expect(document.getElementById('settings-form').closest('.atl')).not.toBeNull()
  })

  it('jumps from the table of contents and writes the section in the address', async () => {
    const scrolled = []
    Element.prototype.scrollIntoView = vi.fn(function scroll() { scrolled.push(this.id) })
    await loaded()
    fireEvent.click(tocLink('settings.tabs.audit'))
    expect(scrolled).toContain('set-sec-audit')
    delete Element.prototype.scrollIntoView
  })

  it('leaves without a question and finds the draft again on the return', async () => {
    render(
      <MemoryRouter initialEntries={['/settings']}>
        <Routes>
          <Route path="/settings" element={<><Link to="/certificates">elsewhere</Link><SettingsPage /></>} />
          <Route path="/certificates" element={<Link to="/settings">back</Link>} />
        </Routes>
      </MemoryRouter>,
    )
    await screen.findByLabelText('system-name')
    await waitFor(() => expect(screen.getByLabelText('syslog-host')).toHaveValue('log.example.com'))
    fireEvent.change(screen.getByLabelText('system-name'), { target: { value: 'PKI 2' } })
    fireEvent.change(screen.getByLabelText('syslog-host'), { target: { value: 'log2.example.com' } })
    await act(async () => { fireEvent.click(screen.getByText('elsewhere')) })
    expect(notificationSpies.showConfirm).not.toHaveBeenCalled()
    await act(async () => { fireEvent.click(await screen.findByText('back')) })
    await waitFor(() => expect(screen.getByLabelText('system-name')).toHaveValue('PKI 2'))
    await waitFor(() => expect(screen.getByLabelText('syslog-host')).toHaveValue('log2.example.com'))
    expect(bar()).toHaveTextContent('sectioned.pendingTitle')
    expect(tocLink('settings.tabs.general')).toHaveTextContent('sectioned.flagModified')
    // Undo forgets the draft: the next visit shows what the server holds
    fireEvent.click(undoButton())
    await act(async () => { fireEvent.click(screen.getByText('elsewhere')) })
    await act(async () => { fireEvent.click(await screen.findByText('back')) })
    await waitFor(() => expect(screen.getByLabelText('syslog-host')).toHaveValue('log.example.com'))
    expect(screen.getByLabelText('system-name')).toHaveValue('PKI')
  }, 20000)

  it('lets a link go without asking when nothing is pending', async () => {
    await loaded()
    await act(async () => { fireEvent.click(screen.getByText('elsewhere')) })
    expect(notificationSpies.showConfirm).not.toHaveBeenCalled()
  })
})
