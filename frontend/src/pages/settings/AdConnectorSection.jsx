import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Btn, ListView, Toolbar, SearchField, EmptyBlock, NoMatch, Pill, RecordList, RecordRow } from '../../components/atelier'
import { Modal, Notice } from '../../components/atelier/Form'
import { adConnectorsService } from '../../services'
import { useNotification } from '../../contexts'
import { formatDate } from '../../lib/utils'
import AdConnectorForm from './AdConnectorForm'

// The probe's verdict next to the enabled switch: only while lookups still act on it, which the
// server decides (health_fresh), so a wrong browser clock cannot hide or keep the badge.
function connectorHealthBadge(connector, t) {
  if (!connector.enabled) return null
  if (!connector.health_fresh) return null
  return {
    up: { tone: 'good', label: t('adConnector.healthStateUp') },
    down: { tone: 'bad', label: t('adConnector.healthStateDown') },
    degraded: { tone: 'warn', label: t('adConnector.healthStateDegraded') },
  }[connector.health?.state] || null
}

export default function AdConnectorSection({ hasPermission }) {
  const { t } = useTranslation()
  const { showSuccess, showError, showWarning, showConfirm } = useNotification()
  const [connectors, setConnectors] = useState([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(null) // a connector, or {} for a new one
  const [testingId, setTestingId] = useState(null)
  const [refusal, setRefusal] = useState(null) // { name, message, profiles, total }
  const [search, setSearch] = useState('')
  const canWrite = hasPermission('write:ad_connector')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const response = await adConnectorsService.list()
      setConnectors(response.data || [])
    } catch (error) {
      showError(error.message || t('messages.errors.loadFailed.generic'))
    } finally {
      setLoading(false)
    }
  }, [showError, t])

  useEffect(() => { load() }, [load])

  const handleSave = async (data) => {
    try {
      if (editing?.id) await adConnectorsService.update(editing.id, data)
      else await adConnectorsService.create(data)
      showSuccess(t('messages.success.update.settings'))
      setEditing(null)
      load()
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.settings'))
    }
  }

  const handleToggle = async (connector) => {
    try {
      await adConnectorsService.update(connector.id, { enabled: !connector.enabled })
      load()
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.settings'))
    }
  }

  const handleTest = async (connector) => {
    setTestingId(connector.id)
    try {
      const response = await adConnectorsService.testSaved(connector.id)
      const message = response.data?.message || t('adConnector.testSuccess')
      // A partial pass is not a pass: it works today only because the reachable DC is up
      if (response.data?.partial) showWarning(message)
      else showSuccess(message)
    } catch (error) {
      showError(error.message || t('adConnector.testFailed'))
    } finally {
      setTestingId(null)
      // The test records its verdict and the domain SID on the row
      load()
    }
  }

  const handleDelete = async (connector) => {
    const ok = await showConfirm(t('adConnector.confirmDelete', { name: connector.name }), {
      title: t('adConnector.deleteTitle'), confirmText: t('common.delete'), variant: 'danger',
    })
    if (!ok) return
    try {
      await adConnectorsService.remove(connector.id)
      showSuccess(t('adConnector.deleted', { name: connector.name }))
      load()
    } catch (error) {
      const profiles = error.data?.details?.profiles
      if (error.status === 409 && Array.isArray(profiles)) {
        setRefusal({
          name: connector.name, message: error.message, profiles,
          total: error.data.details.total ?? profiles.length,
        })
      } else {
        showError(error.message || t('adConnector.deleteFailed'))
      }
    }
  }

  // The search reads the name and the realm, as the product's table did
  const needle = search.trim().toLowerCase()
  const shown = needle ? connectors.filter(c => [c.name, c.realm].some(v => (v || '').toLowerCase().includes(needle))) : connectors
  const servers = (row) => {
    const list = row.servers || []
    if (!list.length) return '—'
    return list.length > 1
      ? t('adConnector.serverSummary', { server: list[0], port: row.port, count: list.length - 1 })
      : `${list[0]}:${row.port}`
  }
  const lastTest = (row) => {
    if (!row.last_test_at) return '—'
    const mark = { success: '✓', partial: '!' }[row.last_test_result] || '✗'
    return `${mark} ${formatDate(row.last_test_at)}`
  }
  const state = (row) => {
    const health = connectorHealthBadge(row, t)
    return (
      <span className="row-actions">
        <Pill tone={row.enabled ? 'good' : 'muted'} label={row.enabled ? t('common.enabled') : t('common.disabled')} />
        {health && <Pill tone={health.tone} label={health.label} />}
      </span>
    )
  }

  const rowActions = (row) => [
    { icon: 'send', label: t('adConnector.testConnection'), onClick: () => { if (testingId !== row.id) handleTest(row) } },
    ...(canWrite ? [
      { icon: row.enabled ? 'block' : 'check', label: row.enabled ? t('common.disable') : t('common.enable'), write: true, onClick: () => handleToggle(row) },
      { icon: 'close', label: t('common.delete'), write: true, onClick: () => handleDelete(row) },
    ] : []),
  ]

  // The connectors as the mockup's module list: the name opens the form, the row holds test, switch and delete
  return (
    <>
      <Notice><strong>{t('adConnector.helpTitle')}</strong>{' '}{t('adConnector.helpDescription')}</Notice>

      <ListView label={t('adConnector.title')} icon="globe" rows={shown} loading={loading}
        title={(row) => row.name} status={state}
        openedId={editing?.id} onOpen={canWrite ? setEditing : undefined}
        toolbar={(
          <Toolbar>
            <SearchField id="ad-connector-search" label={t('common.search')} placeholder={t('adConnector.searchPlaceholder')} value={search} onChange={setSearch} />
          </Toolbar>
        )}
        columns={[
          { id: 'realm', label: t('adConnector.realm'), cell: (row) => row.realm || t('adConnector.noRealm') },
          { id: 'servers', label: t('adConnector.servers'), cell: servers, grow: true },
          { id: 'sid', label: t('adConnector.domainSid'), cell: (row) => (row.domain_sid
            ? <span className="mono" data-testid="domain-sid">{row.domain_sid}</span>
            : <span className="muted">{t('adConnector.domainSidUnknown')}</span>) },
          { id: 'test', label: t('adConnector.testConnection'), cell: lastTest },
          { status: true },
        ]}
        rowActions={rowActions}
        empty={connectors.length ? (
          <NoMatch title={t('common.noResults')} resetLabel={t('common.clear')} onReset={() => setSearch('')} />
        ) : (
          <EmptyBlock id="ad-connectors" icon="globe" title={t('adConnector.notConfigured')} text={t('adConnector.notConfiguredDesc')}
            action={canWrite ? { label: t('adConnector.add'), icon: 'plus', onClick: () => setEditing({}), primary: true } : undefined} />
        )} />

      {canWrite && connectors.length > 0 && (
        <div className="settings-actions">
          <Btn tone="primary" icon="plus" onClick={() => setEditing({})}>{t('adConnector.add')}</Btn>
        </div>
      )}

      <Modal
        open={Boolean(editing)}
        onClose={() => setEditing(null)}
        title={editing?.id ? t('adConnector.editTitle') : t('adConnector.addTitle')}
        size="lg"
      >
        {editing && (
          <AdConnectorForm
            key={editing.id || 'new'}
            config={editing.id ? editing : null}
            onSave={handleSave}
            onCancel={() => setEditing(null)}
          />
        )}
      </Modal>

      <Modal
        open={Boolean(refusal)}
        onClose={() => setRefusal(null)}
        title={t('adConnector.deleteRefusedTitle', { name: refusal?.name })}
        size="sm"
      >
        {refusal && (
          <>
            <p>{t('adConnector.deleteRefused', { count: refusal.total })}</p>
            <div data-testid="refusal-profiles">
              <RecordList>{refusal.profiles.map(profile => <RecordRow key={profile.id} title={profile.name} />)}</RecordList>
            </div>
            {refusal.total > refusal.profiles.length && (
              <p className="small muted">{t('adConnector.deleteRefusedMore', { count: refusal.total - refusal.profiles.length })}</p>
            )}
            <div className="modal-actions">
              <button type="button" className="btn primary" data-write="false" data-action="close-modal" onClick={() => setRefusal(null)}>{t('common.close')}</button>
            </div>
          </>
        )}
      </Modal>
    </>
  )
}
