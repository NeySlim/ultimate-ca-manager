import { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Btn, ListView, Toolbar, SearchField, FilterSelect, EmptyBlock, NoMatch, Pill } from '../../components/atelier'
import { windowsProfilesService } from '../../services'
import { useNotification } from '../../contexts'
import { PROFILE_STATES } from '../../lib/windowsProfile'

const DEBOUNCE_MS = 300
const STATE_TONE = { complete: 'good', keytab_missing: 'warn', connector_failing: 'bad', disabled: 'muted' }

/**
 * The profiles, one server page at a time: the name or realm search, the CA and the state go to
 * the server, so 150 profiles cost one page. `reloadKey` makes the list read again. Drawn as the
 * mockup's module list: the name opens the profile, the footer pages the server's list.
 */
export default function WindowsProfileList({ cas, canWrite, onEdit, onCreate, reloadKey }) {
  const { t, i18n } = useTranslation()
  const { showSuccess, showError, showConfirm } = useNotification()
  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(25)
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [ca, setCa] = useState('')
  const [state, setState] = useState('')
  const [version, setVersion] = useState(0)
  const timer = useRef(null)

  const changeSearch = (value) => {
    setSearch(value)
    clearTimeout(timer.current)
    timer.current = setTimeout(() => { setQuery(value.trim()); setPage(1) }, DEBOUNCE_MS)
  }
  useEffect(() => () => clearTimeout(timer.current), [])

  useEffect(() => {
    let cancelled = false
    const params = { page, per_page: perPage }
    if (query) params.q = query
    if (ca) params.ca = ca
    if (state) params.state = state
    setLoading(true)
    windowsProfilesService.list(params)
      .then((response) => {
        if (cancelled) return
        setRows(response.data || [])
        setTotal(response.meta?.total ?? (response.data || []).length)
      })
      .catch((error) => { if (!cancelled) showError(error.message || t('messages.errors.loadFailed.generic')) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [page, perPage, query, ca, state, version, reloadKey, showError, t])

  const reload = () => setVersion(v => v + 1)

  const toggle = async (profile) => {
    try {
      await windowsProfilesService.update(profile.id, { enabled: !profile.enabled })
      showSuccess(t('messages.success.update.settings'))
      reload()
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.settings'))
    }
  }

  const remove = async (profile) => {
    const ok = await showConfirm(t('xcepWstep.confirmDelete', { name: profile.name }), {
      title: t('xcepWstep.deleteTitle'), confirmText: t('common.delete'), variant: 'danger',
    })
    if (!ok) return
    try {
      await windowsProfilesService.remove(profile.id)
      showSuccess(t('xcepWstep.deleted', { name: profile.name }))
      reload()
    } catch (error) {
      // The server says why: the default profile, or valid certificates issued through it
      showError(error.message || t('xcepWstep.deleteFailed'))
    }
  }

  const rowActions = (row) => canWrite ? [
    { icon: row.enabled ? 'block' : 'check', label: row.enabled ? t('common.disable') : t('common.enable'), write: true, onClick: () => toggle(row) },
    ...(row.is_default ? [] : [{ icon: 'close', label: t('common.delete'), write: true, onClick: () => remove(row) }]),
  ] : []

  const caOptions = (cas || []).filter(c => c.refid).map(c => ({ value: c.refid, label: c.descr || c.common_name }))
  const pages = Math.max(1, Math.ceil(total / perPage))
  const number = new Intl.NumberFormat(i18n?.language || undefined)
  const filtered = Boolean(query || ca || state)
  const resetFilters = () => { clearTimeout(timer.current); setSearch(''); setQuery(''); setCa(''); setState(''); setPage(1) }

  return (
    <>
      <ListView label={t('xcepWstep.profilesTitle')} icon="monitor" rows={rows} loading={loading}
        title={(row) => row.name} status={(row) => <Pill tone={STATE_TONE[row.state] || 'muted'} label={t(`xcepWstep.state.${row.state}`)} />}
        nameExtra={(row) => (
          <>
            {row.is_default && <> <Pill icon="pin" label={t('xcepWstep.defaultBadge')} /></>}
            {!row.realm && row.is_default && <span className="rl-meta warn">{t('xcepWstep.noRealmKerberosRefused', { name: row.name })}</span>}
          </>
        )}
        onOpen={onEdit}
        toolbar={(
          <Toolbar>
            <SearchField id="windows-profile-search" label={t('common.search')} placeholder={t('xcepWstep.searchPlaceholder')} value={search} onChange={changeSearch} />
            <FilterSelect id="windows-profile-ca" label={t('xcepWstep.issuingCa')} value={ca} onChange={(v) => { setCa(v); setPage(1) }}
              options={[{ value: '', label: t('xcepWstep.allCas') }, ...caOptions]} />
            <FilterSelect id="windows-profile-state" label={t('common.status')} value={state} onChange={(v) => { setState(v); setPage(1) }}
              options={[{ value: '', label: t('common.allStatus') }, ...PROFILE_STATES.map(value => ({ value, label: t(`xcepWstep.state.${value}`) }))]} />
          </Toolbar>
        )}
        columns={[
          { id: 'realm', label: t('xcepWstep.realm'), cell: (row) => (row.realm
            ? <span className="mono">{row.realm}</span>
            : <Pill tone="warn" label={t('xcepWstep.realmUnset')} />) },
          { id: 'ca', label: t('xcepWstep.issuingCa'), cell: (row) => row.issuing_ca_name || '—', grow: true },
          { id: 'connector', label: t('xcepWstep.connector'), cell: (row) => (row.connector_name
            ? <>{row.connector_name}{row.connector_health === 'down' && <> <Pill tone="bad" label={t('adConnector.healthStateDown')} /></>}</>
            : <span className="muted">{t('xcepWstep.noConnector')}</span>) },
          { status: true },
        ]}
        rowActions={rowActions}
        empty={filtered ? (
          <NoMatch title={t('common.noResults')} resetLabel={t('table.clearFilters')} onReset={resetFilters} />
        ) : (
          <EmptyBlock id="windows-profiles" icon="monitor" title={t('xcepWstep.noProfiles')} text={t('xcepWstep.noProfilesDesc')}
            action={canWrite ? { label: t('xcepWstep.addProfile'), icon: 'plus', onClick: onCreate, primary: true } : undefined} />
        )}
        footer={total > 0 ? {
          range: t('table.range', { start: number.format((page - 1) * perPage + 1), end: number.format(Math.min(page * perPage, total)), total }),
          pagination: { page, pages, perPage, onPage: setPage, onPerPage: (value) => { setPerPage(value); setPage(1) } },
        } : undefined} />
      {/* An empty list without filters offers Add in its empty block, not twice */}
      {canWrite && (loading || filtered || rows.length > 0) && (
        <div className="settings-actions">
          <Btn tone="primary" icon="plus" onClick={onCreate}>{t('xcepWstep.addProfile')}</Btn>
        </div>
      )}
    </>
  )
}
