import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import ReactMarkdown from 'react-markdown'
import { Btn, ListView, Toolbar, SearchField, EmptyBlock, NoMatch, Pill, useClientList, useSortParam } from '../../components/atelier'
import { Notice } from '../../components/atelier/Form'
import { formatDate } from '../../lib/utils'

// The help's paragraphs run inline in the notice; its list keeps its items
const NOTICE_MARKDOWN = { p: ({ children }) => <>{children} </> }
// A connection's authentication method in the words of its form
const AUTH_WORDS = { certificate: 'msca.authCertificate', kerberos: 'msca.authKerberos', basic: 'msca.authBasic' }
// The connections by name, the sort in the address under this list's scope (the settings stack their sections)
const BY_NAME = { key: 'name', asc: true }
const SORT_KEYS = ['name', 'server', 'template', 'auth', 'test', 'state']

export default function MicrosoftCASection({ mscaConnections, mscaLoading, mscaTesting, handleMscaCreate, handleMscaEdit, handleMscaToggle, handleMscaTest, handleMscaSyncCrl, handleMscaPublishCrl, handleMscaInventorySync, handleMscaCaControl, setMscaConfirmDelete, hasPermission }) {
  const { t } = useTranslation()
  const [search, setSearch] = useState('')
  // The outcome of a test or a sync in words, not a check mark
  const outcome = (ok) => t(ok ? 'common.success' : 'common.failed')
  // Test, enable and edit write the connection (write:settings), deleting it is delete:settings
  const canWrite = hasPermission('write:settings')
  const canDelete = hasPermission('delete:settings')
  const admin = hasPermission('admin:system')
  const sep = t('work.sep')
  const auth = (row) => (AUTH_WORDS[row.auth_method] ? t(AUTH_WORDS[row.auth_method]) : row.auth_method)

  // The search reads the name, the server, the CA's name and the template
  const needle = search.trim().toLowerCase()
  const shown = needle
    ? mscaConnections.filter((c) => [c.name, c.server, c.ca_name, c.default_template].some((v) => (v || '').toLowerCase().includes(needle)))
    : mscaConnections
  const sortParam = useSortParam(BY_NAME, SORT_KEYS, { scope: 'msca' })
  const list = useClientList(shown, {
    sortParam,
    resetKey: needle,
    sorts: {
      name: (r) => r.name, server: (r) => r.server, template: (r) => r.default_template || null, auth: auth,
      test: (r) => (r.last_test_at ? Date.parse(r.last_test_at) : null), state: (r) => (r.enabled ? 0 : 1),
    },
  })

  const lastTest = (row) => (row.last_test_at
    ? `${outcome(row.last_test_result === 'success')}, ${formatDate(row.last_test_at)}` : '—')
  // The syncs and the admin channel a connection runs, each on its line
  const runs = (row) => {
    const lines = [
      row.crl_sync_enabled && row.last_crl_sync_at
        && `${t('msca.lastCrlSync')}${sep}${outcome(row.last_crl_sync_result?.startsWith('success'))}, ${formatDate(row.last_crl_sync_at)}`,
      row.inventory_sync_enabled && row.last_inventory_sync_at
        && `${t('msca.lastInventorySync')}${sep}${outcome(row.last_inventory_sync_result?.startsWith('success'))}, ${formatDate(row.last_inventory_sync_at)}`,
      row.winrm_enabled && `${t('msca.adminChannel')}${sep}WinRM ${row.winrm_transport} · ${row.winrm_host || row.server}:${row.winrm_port}`,
    ].filter(Boolean)
    return lines.length ? lines.map((line) => <span key={line} className="rl-meta">{line}</span>) : '—'
  }
  const rowActions = (row) => [
    ...(canWrite ? [{ icon: 'send', label: t('msca.testConnection'), disabled: mscaTesting, onClick: () => handleMscaTest(row) }] : []),
    ...(row.winrm_enabled && admin ? [{ icon: 'activity', label: t('msca.caControl'), disabled: !row.enabled, onClick: () => handleMscaCaControl(row) }] : []),
    ...(row.crl_sync_enabled && hasPermission('write:certificates')
      ? [{ icon: 'refresh', label: t('msca.syncCrlNow'), write: true, disabled: mscaTesting || !row.enabled, onClick: () => handleMscaSyncCrl(row) }] : []),
    ...(row.winrm_enabled && admin
      ? [{ icon: 'crl', label: t('msca.publishCrl'), write: true, disabled: mscaTesting || !row.enabled, onClick: () => handleMscaPublishCrl(row) }] : []),
    ...(row.inventory_sync_enabled && admin
      ? [{ icon: 'download', label: t('msca.inventorySyncNow'), write: true, disabled: mscaTesting || !row.enabled, onClick: () => handleMscaInventorySync(row) }] : []),
    ...(canWrite ? [
      { icon: row.enabled ? 'block' : 'check', label: row.enabled ? t('common.disable') : t('common.enable'), write: true, onClick: () => handleMscaToggle(row) },
      { icon: 'settings', label: t('common.edit'), onClick: () => handleMscaEdit(row) },
    ] : []),
    ...(canDelete ? [{ icon: 'close', label: t('common.delete'), write: true, onClick: () => setMscaConfirmDelete(row) }] : []),
  ]

  // The module list of the Active Directory section, under the help
  return (
    <>
      <Notice><strong>{t('msca.helpTitle')}</strong>{' '}<ReactMarkdown components={NOTICE_MARKDOWN}>{t('msca.helpDescription')}</ReactMarkdown></Notice>
      <ListView label={t('settings.tabs.microsoftCA')} icon="plug" list={list} nameSort="name" loading={mscaLoading} scrollId="msca-scroll" cardActions
        title={(row) => row.name}
        status={(row) => <Pill tone={row.enabled ? 'good' : 'muted'} label={row.enabled ? t('common.enabled') : t('common.disabled')} />}
        onOpen={canWrite ? handleMscaEdit : undefined}
        toolbar={(
          <Toolbar>
            <SearchField id="msca-search" label={t('common.search')} placeholder={t('msca.searchPlaceholder')} value={search} onChange={setSearch} />
          </Toolbar>
        )}
        columns={[
          { id: 'server', label: t('msca.serverColumn'), cell: (row) => <span className="mono">{row.server}{row.ca_name ? ` · ${row.ca_name}` : ''}</span>,
            title: (row) => row.server, kind: 'text', priority: 2, grow: true, sort: 'server' },
          { id: 'template', label: t('msca.templateColumn'), cell: (row) => row.default_template || '—', kind: 'text', priority: 3, sort: 'template' },
          { id: 'auth', label: t('msca.authColumn'), cell: (row) => <Pill icon="key" label={auth(row)} />, kind: 'fit', priority: 3, sort: 'auth' },
          { id: 'test', label: t('msca.lastTestColumn'), cell: lastTest, kind: 'fit', priority: 3, labelled: true, sort: 'test' },
          { id: 'runs', label: t('msca.runsColumn'), cell: runs, kind: 'text', priority: 4 },
          { status: true, sort: 'state' },
        ]}
        rowActions={rowActions}
        empty={mscaConnections.length ? (
          <NoMatch title={t('common.noResults')} resetLabel={t('common.clear')} onReset={() => setSearch('')} />
        ) : (
          <EmptyBlock id="msca" icon="plug" title={t('msca.noConnections')} text={t('msca.noConnectionsDesc')}
            action={admin ? { label: t('msca.addConnection'), icon: 'plus', onClick: handleMscaCreate, primary: true } : undefined} />
        )}
        footer={list.paged ? { range: t('table.range', { start: list.start, end: list.end, total: list.total }) } : undefined} />
      {admin && mscaConnections.length > 0 && (
        <div className="settings-actions">
          <Btn tone="primary" icon="plus" onClick={handleMscaCreate}>{t('msca.addConnection')}</Btn>
        </div>
      )}
    </>
  )
}
