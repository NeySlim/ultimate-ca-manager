import { useState, useEffect, useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { IdentificationBadge, TestTube, Power, PencilSimple, Plus, Trash, ArrowsClockwise } from '@phosphor-icons/react'
import { Button, Badge, HelpCard, DetailHeader, DetailContent, Modal, ResponsiveDataTable } from '../../components'
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
    up: { variant: 'success', label: t('adConnector.healthStateUp') },
    down: { variant: 'danger', label: t('adConnector.healthStateDown') },
    degraded: { variant: 'warning', label: t('adConnector.healthStateDegraded') },
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

  const columns = useMemo(() => [
    {
      key: 'name',
      header: t('adConnector.name'),
      priority: 1,
      render: (value, row) => (
        <div className="min-w-0">
          <div className="font-medium text-text-primary truncate">{value}</div>
          <div className="text-xs text-text-secondary truncate">{row.realm || t('adConnector.noRealm')}</div>
        </div>
      ),
    },
    {
      key: 'servers',
      header: t('adConnector.servers'),
      hideOnMobile: true,
      render: (servers, row) => {
        const list = servers || []
        if (!list.length) return <span className="text-text-tertiary">-</span>
        return list.length > 1
          ? t('adConnector.serverSummary', { server: list[0], port: row.port, count: list.length - 1 })
          : `${list[0]}:${row.port}`
      },
    },
    {
      key: 'enabled',
      header: t('common.status'),
      priority: 2,
      render: (_value, row) => {
        const health = connectorHealthBadge(row, t)
        return (
          <div className="flex items-center gap-1 flex-wrap">
            <Badge variant={row.enabled ? 'success' : 'secondary'} size="sm">
              {row.enabled ? t('common.enabled') : t('common.disabled')}
            </Badge>
            {health && <Badge variant={health.variant} size="sm">{health.label}</Badge>}
          </div>
        )
      },
    },
    {
      key: 'domain_sid',
      header: t('adConnector.domainSid'),
      hideOnMobile: true,
      render: (value) => value
        ? <span className="font-mono text-xs break-all" data-testid="domain-sid">{value}</span>
        : <span className="text-xs text-text-tertiary">{t('adConnector.domainSidUnknown')}</span>,
    },
    {
      key: 'last_test_at',
      header: t('adConnector.testConnection'),
      hideOnMobile: true,
      render: (value, row) => {
        if (!value) return <span className="text-text-tertiary">-</span>
        const mark = { success: '✓', partial: '!' }[row.last_test_result] || '✗'
        return `${mark} ${formatDate(value)}`
      },
    },
  ], [t])

  const rowActions = (row) => {
    const actions = [{
      label: t('adConnector.testConnection'),
      icon: testingId === row.id ? ArrowsClockwise : TestTube,
      onClick: () => handleTest(row),
    }]
    if (canWrite) {
      actions.push(
        { label: row.enabled ? t('common.disable') : t('common.enable'), icon: Power, onClick: () => handleToggle(row) },
        { label: t('common.edit'), icon: PencilSimple, onClick: () => setEditing(row) },
        { label: t('common.delete'), icon: Trash, variant: 'danger', onClick: () => handleDelete(row) },
      )
    }
    return actions
  }

  return (
    <DetailContent>
      <DetailHeader
        icon={IdentificationBadge}
        title={t('adConnector.title')}
        subtitle={t('adConnector.subtitle')}
      />

      <HelpCard variant="info" title={t('adConnector.helpTitle')} className="mb-4">
        {t('adConnector.helpDescription')}
      </HelpCard>

      <ResponsiveDataTable
        data={connectors}
        columns={columns}
        keyField="id"
        loading={loading}
        searchable
        searchKeys={['name', 'realm']}
        searchPlaceholder={t('adConnector.searchPlaceholder')}
        rowActions={rowActions}
        toolbarActions={canWrite ? (
          <Button type="button" size="sm" onClick={() => setEditing({})}>
            <Plus size={14} /> {t('adConnector.add')}
          </Button>
        ) : undefined}
        emptyIcon={IdentificationBadge}
        emptyTitle={t('adConnector.notConfigured')}
        emptyDescription={t('adConnector.notConfiguredDesc')}
      />

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
        size="md"
      >
        {refusal && (
          <div className="p-4 space-y-3">
            <p className="text-sm text-text-primary">{t('adConnector.deleteRefused', { count: refusal.total })}</p>
            <ul className="list-disc pl-5 text-sm text-text-primary" data-testid="refusal-profiles">
              {refusal.profiles.map(profile => <li key={profile.id}>{profile.name}</li>)}
            </ul>
            <div className="flex justify-end pt-2 border-t border-border">
              <Button type="button" variant="secondary" onClick={() => setRefusal(null)}>{t('common.close')}</Button>
            </div>
          </div>
        )}
      </Modal>
    </DetailContent>
  )
}
