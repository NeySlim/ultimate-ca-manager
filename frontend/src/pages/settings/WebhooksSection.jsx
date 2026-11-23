import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Btn, ListView, Toolbar, SearchField, EmptyBlock, NoMatch, Pill, useClientList, useSortParam } from '../../components/atelier'
import { webhookEventLabel } from './WebhookForm'
import WebhookDeliveriesModal from './WebhookDeliveriesModal'

// The webhooks by name, the sort in the address under this list's scope (the settings stack their sections)
const BY_NAME = { key: 'name', asc: true }
const SORT_KEYS = ['name', 'url', 'events', 'state']

export default function WebhooksSection({ webhooks, webhooksLoading, webhookTesting, handleWebhookCreate, handleWebhookEdit, handleWebhookToggle, handleWebhookTest, setWebhookConfirmDelete, hasPermission }) {
  const { t } = useTranslation()
  const [deliveriesFor, setDeliveriesFor] = useState(null)
  const [search, setSearch] = useState('')
  // Test, enable and edit write a webhook (write:settings), deleting one is delete:settings
  const canWrite = hasPermission('write:settings')
  const canDelete = hasPermission('delete:settings')
  const canAdd = hasPermission('admin:system')

  // The search reads the name, the address and the events, by their code or their words
  const needle = search.trim().toLowerCase()
  const words = (hook) => [hook.name, hook.url, ...(hook.events || []).flatMap((ev) => [ev, webhookEventLabel(t, ev)])]
  const shown = needle ? webhooks.filter((hook) => words(hook).some((v) => (v || '').toLowerCase().includes(needle))) : webhooks
  const sortParam = useSortParam(BY_NAME, SORT_KEYS, { scope: 'webhooks' })
  const list = useClientList(shown, {
    sortParam,
    resetKey: needle,
    sorts: { name: (r) => r.name, url: (r) => r.url, events: (r) => (r.events || []).length, state: (r) => (r.enabled ? 0 : 1) },
  })

  const events = (row) => {
    const all = row.events || []
    if (!all.length) return '—'
    return `${all.slice(0, 3).map((ev) => webhookEventLabel(t, ev)).join(', ')}${all.length > 3 ? ` +${all.length - 3}` : ''}`
  }
  const rowActions = (row) => [
    { icon: 'clock', label: t('webhooks.deliveries.title', { name: row.name }), onClick: () => setDeliveriesFor(row) },
    ...(canWrite ? [
      { icon: 'send', label: t('webhooks.test'), disabled: webhookTesting === row.id, onClick: () => handleWebhookTest(row) },
      { icon: row.enabled ? 'block' : 'check', label: row.enabled ? t('common.disable') : t('common.enable'), write: true, onClick: () => handleWebhookToggle(row) },
      { icon: 'settings', label: t('common.edit'), onClick: () => handleWebhookEdit(row) },
    ] : []),
    ...(canDelete ? [{ icon: 'close', label: t('common.delete'), write: true, onClick: () => setWebhookConfirmDelete(row) }] : []),
  ]

  // The module list of the Active Directory section: the name opens the form, the row holds the actions
  return (
    <>
      <ListView label={t('webhooks.title')} icon="bell" list={list} nameSort="name" loading={webhooksLoading} scrollId="webhooks-scroll" cardActions
        title={(row) => row.name}
        status={(row) => <Pill tone={row.enabled ? 'good' : 'muted'} label={row.enabled ? t('common.enabled') : t('common.disabled')} />}
        onOpen={canWrite ? handleWebhookEdit : undefined}
        toolbar={(
          <Toolbar>
            <SearchField id="webhook-search" label={t('common.search')} placeholder={t('webhooks.searchPlaceholder')} value={search} onChange={setSearch} />
          </Toolbar>
        )}
        columns={[
          { id: 'url', label: t('webhooks.url'), cell: (row) => <span className="mono">{row.url}</span>, title: (row) => row.url, kind: 'text', priority: 2, grow: true, sort: 'url' },
          { id: 'events', label: t('webhooks.events'), cell: events, title: (row) => (row.events || []).map((ev) => webhookEventLabel(t, ev)).join(', ') || undefined, kind: 'text', priority: 3, sort: 'events' },
          { status: true, sort: 'state' },
        ]}
        rowActions={rowActions}
        empty={webhooks.length ? (
          <NoMatch title={t('common.noResults')} resetLabel={t('common.clear')} onReset={() => setSearch('')} />
        ) : (
          <EmptyBlock id="webhooks" icon="bell" title={t('webhooks.noWebhooks')} text={t('webhooks.noWebhooksDescription')}
            action={canAdd ? { label: t('webhooks.addWebhook'), icon: 'plus', onClick: handleWebhookCreate, primary: true } : undefined} />
        )}
        footer={list.paged ? { range: t('table.range', { start: list.start, end: list.end, total: list.total }) } : undefined} />

      {canAdd && webhooks.length > 0 && (
        <div className="settings-actions">
          <Btn tone="primary" icon="plus" onClick={handleWebhookCreate}>{t('webhooks.addWebhook')}</Btn>
        </div>
      )}
      <WebhookDeliveriesModal
        webhook={deliveriesFor}
        onClose={() => setDeliveriesFor(null)}
        canRetry={hasPermission('write:settings') || hasPermission('admin:system')}
      />
    </>
  )
}
