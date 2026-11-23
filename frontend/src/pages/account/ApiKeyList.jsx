import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ListView, Toolbar, SearchField, EmptyBlock, NoMatch, Pill, IconBtn, useClientList, useSortParam } from '../../components/atelier'
import { apiKeyScopeLabel } from '../../lib/apiKeyScopes'
import { formatDate } from '../../lib/utils'

// The keys in use first, then the expired and the revoked ones: the default order, in the address under this list's scope
const IN_USE_FIRST = { key: 'state', asc: true }
const SORT_KEYS = ['name', 'prefix', 'created', 'used', 'expires', 'state']
const stateOf = (key) => (!key.is_active ? 2 : key.is_expired ? 1 : 0)
const date = (v) => (v ? Date.parse(v) : null)

/** The account's API keys as the settings tables: revoke a key in use, delete one that no longer works. */
export default function ApiKeyList({ keys, loading, onRevoke, onDelete, onCopy }) {
  const { t } = useTranslation()
  const [search, setSearch] = useState('')
  const needle = search.trim().toLowerCase()
  const shown = needle ? keys.filter((k) => [k.name, k.key_prefix].some((v) => (v || '').toLowerCase().includes(needle))) : keys
  const sortParam = useSortParam(IN_USE_FIRST, SORT_KEYS, { scope: 'keys' })
  const list = useClientList(shown, {
    sortParam,
    resetKey: needle,
    sorts: {
      name: (k) => k.name, prefix: (k) => k.key_prefix || null, created: (k) => date(k.created_at),
      used: (k) => date(k.last_used_at), expires: (k) => date(k.expires_at), state: stateOf,
    },
  })

  const STATES = [['good', 'common.active'], ['muted', 'common.expired'], ['muted', 'common.revoked']]
  const status = (key) => { const [tone, label] = STATES[stateOf(key)]; return <Pill tone={tone} label={t(label)} /> }
  const prefix = (key) => (key.key_prefix ? (
    <span className="row-actions">
      <span className="mono">{key.key_prefix}…</span>
      <IconBtn icon="copy" quiet label={t('common.copy')} onClick={(e) => { e.stopPropagation(); onCopy(key.key_prefix) }} />
    </span>
  ) : <span className="muted">{t('account.apiKeyPrefixUnavailable')}</span>)
  const rowActions = (key) => (stateOf(key) === 0
    ? [{ icon: 'block', label: t('common.revoke'), write: true, onClick: () => onRevoke(key.id) }]
    : [{ icon: 'close', label: t('common.delete'), write: true, onClick: () => onDelete(key.id) }])

  return (
    <ListView label={t('account.yourAPIKeys')} icon="key" list={list} nameSort="name" loading={loading} scrollId="api-keys-scroll" cardActions
      title={(key) => key.name} status={status}
      toolbar={(
        <Toolbar>
          <SearchField id="api-key-search" label={t('common.search')} placeholder={t('account.apiKeySearchPlaceholder')} value={search} onChange={setSearch} />
        </Toolbar>
      )}
      columns={[
        { id: 'prefix', label: t('account.apiKeyPrefix'), cell: prefix, kind: 'fit', priority: 2, sort: 'prefix' },
        { id: 'scope', label: t('common.permissions'), cell: (key) => (key.permissions ? apiKeyScopeLabel(t, key.permissions) : '—'), kind: 'text', priority: 3, grow: true },
        { id: 'created', label: t('common.created'), cell: (key) => formatDate(key.created_at), kind: 'fit', priority: 4, sort: 'created' },
        { id: 'used', label: t('account.apiKeyLastUsed'), cell: (key) => (key.last_used_at ? formatDate(key.last_used_at) : t('common.never')), kind: 'fit', priority: 3, sort: 'used' },
        { id: 'expires', label: t('common.expires'), cell: (key) => (key.expires_at ? formatDate(key.expires_at) : '—'), kind: 'fit', priority: 4, sort: 'expires' },
        { status: true, sort: 'state' },
      ]}
      rowActions={rowActions}
      empty={keys.length ? (
        <NoMatch title={t('common.noResults')} resetLabel={t('common.clear')} onReset={() => setSearch('')} />
      ) : (
        <EmptyBlock id="api-keys" icon="key" title={t('account.noAPIKeys')} text={t('account.createKeyToAccess')} />
      )}
      footer={list.paged ? { range: t('table.range', { start: list.start, end: list.end, total: list.total }) } : undefined} />
  )
}
