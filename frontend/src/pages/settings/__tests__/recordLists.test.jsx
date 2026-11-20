/**
 * SSO providers, webhooks and Microsoft AC connections as the mockup's record list: one line
 * per record, named icon actions, and only the actions the API grants to the viewer.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import '../../__tests__/pageRenderingSetup.jsx'
import SsoSection from '../SsoSection'
import WebhooksSection from '../WebhooksSection'
import MicrosoftCASection from '../MicrosoftCASection'
import BackupSection from '../BackupSection'
import { blockedWhileSuspended } from '../../../components/shell/__tests__/writeGuardProbe'

vi.mock('../WebhookDeliveriesModal', () => ({ default: () => null }))

const can = (...granted) => (p) => granted.includes(p)
const noop = vi.fn()

const sso = (perm) => render(
  <SsoSection ssoProviders={[{ id: 1, provider_type: 'ldap', name: 'corp', enabled: true }]} ssoLoading={false}
    handleSsoCreate={noop} handleSsoEdit={noop} handleSsoToggle={noop} handleSsoTest={noop}
    setSsoConfirmDelete={noop} hasPermission={perm} />,
)
const hooks = (perm) => render(
  <WebhooksSection webhooks={[{ id: 7, name: 'ops', url: 'https://hook.example.com', enabled: true, events: ['certificate.issued'] }]}
    webhooksLoading={false} handleWebhookCreate={noop} handleWebhookEdit={noop} handleWebhookToggle={noop}
    handleWebhookTest={noop} setWebhookConfirmDelete={noop} hasPermission={perm} />,
)
const msca = (perm) => render(
  <MicrosoftCASection mscaConnections={[{ id: 3, name: 'adcs', server: 'dc.example.com', enabled: true, auth_method: 'basic', default_template: 'User' }]}
    mscaLoading={false} handleMscaCreate={noop} handleMscaEdit={noop} handleMscaToggle={noop} handleMscaTest={noop}
    handleMscaSyncCrl={noop} handleMscaPublishCrl={noop} handleMscaInventorySync={noop} handleMscaCaControl={noop}
    setMscaConfirmDelete={noop} hasPermission={perm} />,
)

describe('settings record lists', () => {
  it('lists the SSO providers one per line with named actions', () => {
    sso(can('read:sso', 'write:sso', 'delete:sso'))
    const items = screen.getAllByRole('listitem')
    expect(items).toHaveLength(3)
    expect(items[0].closest('ul')).toHaveClass('sf-records')
    for (const name of ['sso.testConnection', 'sso.disable', 'common.edit', 'common.delete']) {
      expect(within(items[0]).getByRole('button', { name })).toBeInTheDocument()
    }
  })

  it('keeps the SSO write and delete actions from a reader', () => {
    sso(can('read:sso'))
    const [ldap] = screen.getAllByRole('listitem')
    expect(within(ldap).queryByRole('button', { name: 'common.edit' })).toBeNull()
    expect(within(ldap).queryByRole('button', { name: 'common.delete' })).toBeNull()
  })

  it('lists the webhooks with their address and events, actions by permission', () => {
    hooks(can('read:settings', 'write:settings'))
    const [row] = screen.getAllByRole('listitem')
    expect(row).toHaveTextContent('https://hook.example.com')
    expect(within(row).getByRole('button', { name: 'webhooks.test' })).toBeInTheDocument()
    expect(within(row).queryByRole('button', { name: 'common.delete' })).toBeNull()
  })

  it('lists the Microsoft AC connections, edit kept from a reader', () => {
    msca(can('read:settings'))
    const [row] = screen.getAllByRole('listitem')
    expect(row.closest('ul')).toHaveClass('sf-records')
    expect(row).toHaveTextContent('dc.example.com')
    expect(within(row).queryByRole('button', { name: 'common.edit' })).toBeNull()
  })

  it('lists the archives with a size in units and a date in the reader format', () => {
    render(
      <BackupSection settings={{}} updateSetting={noop} hasPermission={can('admin:system')}
        backups={[{ filename: 'ucm_backup_1.ucmbkp', size: '1.5 MB', size_bytes: 1.5 * 1024 * 1024, created_at: '2026-11-20 10:05:00 UTC' }]}
        backupMeta={{ total: 1, total_size_bytes: 1.5 * 1024 * 1024 }} updateBackupQuery={noop} />,
    )
    const row = screen.getByText('ucm_backup_1.ucmbkp').closest('li')
    expect(row.closest('ul')).toHaveClass('sf-records')
    expect(row.textContent).not.toContain('UTC')
    expect(row.textContent).toMatch(/1[.,]5\s?(MB|Mo)/)
    expect(within(row).getByRole('button', { name: 'common.download' })).toBeInTheDocument()
  })

  it('says the outcome of a Microsoft AC test and syncs in words, without check marks', () => {
    render(
      <MicrosoftCASection mscaConnections={[{ id: 3, name: 'adcs', server: 'dc.example.com', enabled: true, auth_method: 'basic',
        default_template: 'User', last_test_at: '2026-11-20T10:00:00Z', last_test_result: 'success',
        crl_sync_enabled: true, last_crl_sync_at: '2026-11-20T10:00:00Z', last_crl_sync_result: 'error: timeout' }]}
        mscaLoading={false} handleMscaCreate={noop} handleMscaEdit={noop} handleMscaToggle={noop} handleMscaTest={noop}
        handleMscaSyncCrl={noop} handleMscaPublishCrl={noop} handleMscaInventorySync={noop} handleMscaCaControl={noop}
        setMscaConfirmDelete={noop} hasPermission={can('read:settings')} />,
    )
    const row = screen.getAllByRole('listitem')[0]
    expect(row.textContent).not.toMatch(/[✓✗]/)
    expect(row.textContent).toMatch(/Success|common\.success/)
    expect(row.textContent).toMatch(/Failed|common\.failed/)
  })
})

describe('settings record lists: write guard', () => {
  it('suspends Add a webhook with the other writes', () => {
    hooks(can('read:settings', 'write:settings', 'admin:system'))
    expect(blockedWhileSuspended(screen.getByRole('button', { name: /webhooks.addWebhook/ }))).toBe(true)
  })

  it('suspends Add a connection with the other writes', () => {
    msca(can('read:settings', 'admin:system'))
    expect(blockedWhileSuspended(screen.getByRole('button', { name: /msca.addConnection/ }))).toBe(true)
  })

  it('suspends Create a backup and Clean up now with the other writes', () => {
    render(
      <BackupSection settings={{}} updateSetting={noop} hasPermission={can('admin:system', 'write:settings')}
        backups={[{ filename: 'ucm_backup_1.ucmbkp', size: '1.5 MB', size_bytes: 1.5 * 1024 * 1024, created_at: '2026-11-20 10:05:00 UTC' }]}
        backupMeta={{ total: 1, total_size_bytes: 1.5 * 1024 * 1024 }} updateBackupQuery={noop} setShowBackupModal={noop} handleRunRetention={noop} />,
    )
    expect(blockedWhileSuspended(screen.getByRole('button', { name: /settings.createBackup/ }))).toBe(true)
    expect(blockedWhileSuspended(screen.getByRole('button', { name: /settings.backupCleanupNow/ }))).toBe(true)
  })
})
