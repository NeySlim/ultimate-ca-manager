import { useState, useEffect, useMemo, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus, PencilSimple, Power, Trash, WindowsLogo } from '@phosphor-icons/react'
import { Badge, Button, ResponsiveDataTable } from '../../components'
import { windowsProfilesService } from '../../services'
import { useNotification } from '../../contexts'
import { PROFILE_STATES } from '../../lib/windowsProfile'

const DEBOUNCE_MS = 300
const STATE_VARIANT = { complete: 'success', keytab_missing: 'warning', connector_failing: 'danger', disabled: 'secondary' }

/**
 * The profiles, one server page at a time: the name or realm search, the CA and the state go to
 * the server, so 150 profiles cost one page. `reloadKey` makes the list read again.
 */
export default function WindowsProfileList({ cas, canWrite, onEdit, onCreate, reloadKey }) {
  const { t } = useTranslation()
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

  const columns = useMemo(() => [
    {
      key: 'name',
      header: t('xcepWstep.profileName'),
      priority: 1,
      render: (value, row) => (
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium text-text-primary truncate">{value}</span>
            {row.is_default && <Badge variant="info" size="sm">{t('xcepWstep.defaultBadge')}</Badge>}
          </div>
          {!row.realm && row.is_default && (
            <div className="text-xs status-warning-text">{t('xcepWstep.noRealmKerberosRefused', { name: row.name })}</div>
          )}
        </div>
      ),
    },
    {
      key: 'realm',
      header: t('xcepWstep.realm'),
      priority: 2,
      render: (value) => value
        ? <span className="font-mono text-xs">{value}</span>
        : <Badge variant="warning" size="sm">{t('xcepWstep.realmUnset')}</Badge>,
    },
    {
      key: 'issuing_ca_name',
      header: t('xcepWstep.issuingCa'),
      hideOnMobile: true,
      render: (value) => value || <span className="text-text-tertiary">-</span>,
    },
    {
      key: 'connector_name',
      header: t('xcepWstep.connector'),
      hideOnMobile: true,
      render: (value, row) => value
        ? (
          <span className="flex items-center gap-1">
            {value}
            {row.connector_health === 'down' && <Badge variant="danger" size="sm">{t('adConnector.healthStateDown')}</Badge>}
          </span>
        )
        : <span className="text-text-tertiary">{t('xcepWstep.noConnector')}</span>,
    },
    {
      key: 'state',
      header: t('common.status'),
      priority: 3,
      render: (value) => <Badge variant={STATE_VARIANT[value] || 'secondary'} size="sm">{t(`xcepWstep.state.${value}`)}</Badge>,
    },
  ], [t])

  const rowActions = (row) => canWrite ? [
    { label: t('common.edit'), icon: PencilSimple, onClick: () => onEdit(row) },
    { label: row.enabled ? t('common.disable') : t('common.enable'), icon: Power, onClick: () => toggle(row) },
    ...(row.is_default ? [] : [{ label: t('common.delete'), icon: Trash, variant: 'danger', onClick: () => remove(row) }]),
  ] : [{ label: t('xcepWstep.viewProfile'), icon: PencilSimple, onClick: () => onEdit(row) }]

  const caOptions = (cas || []).filter(c => c.refid).map(c => ({ value: c.refid, label: c.descr || c.common_name }))

  return (
    <ResponsiveDataTable
      data={rows}
      columns={columns}
      keyField="id"
      loading={loading}
      onRowClick={onEdit}
      rowActions={rowActions}
      searchable
      externalSearch={search}
      onSearchChange={changeSearch}
      searchPlaceholder={t('xcepWstep.searchPlaceholder')}
      toolbarFilters={[
        {
          key: 'ca', label: t('xcepWstep.issuingCa'), value: ca, placeholder: t('xcepWstep.allCas'), options: caOptions,
          onChange: (v) => { setCa(v); setPage(1) },
        },
        {
          key: 'state', label: t('common.status'), value: state, placeholder: t('common.allStatus'),
          options: PROFILE_STATES.map(value => ({ value, label: t(`xcepWstep.state.${value}`) })),
          onChange: (v) => { setState(v); setPage(1) },
        },
      ]}
      toolbarActions={canWrite ? (
        <Button type="button" size="sm" onClick={onCreate}>
          <Plus size={14} /> {t('xcepWstep.addProfile')}
        </Button>
      ) : undefined}
      pagination={{
        page, total, perPage,
        onChange: setPage,
        onPerPageChange: (value) => { setPerPage(value); setPage(1) },
      }}
      emptyIcon={WindowsLogo}
      emptyTitle={t('xcepWstep.noProfiles')}
      emptyDescription={t('xcepWstep.noProfilesDesc')}
    />
  )
}
