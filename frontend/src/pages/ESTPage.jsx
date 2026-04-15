/**
 * EST Management Page
 * Enrollment over Secure Transport (RFC 7030) configuration and information
 */
import { useState, useEffect, useMemo, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Globe, Gear, Copy, Info, ShieldCheck, Plugs, Warning, CheckCircle,
  ChartBar, Lock, ArrowsClockwise
} from '@phosphor-icons/react'
import {
  ResponsiveLayout,
  Button, Input, Select, Card,
  LoadingSpinner, EmptyState, HelpCard,
  CompactStats
} from '../components'
import { estService, casService } from '../services'
import { useNotification } from '../contexts'
import { usePermission } from '../hooks'
import { ToggleSwitch } from '../components/ui/ToggleSwitch'

export default function ESTPage() {
  const { t } = useTranslation()
  const { showSuccess, showError, showInfo } = useNotification()
  const { hasPermission, canWrite } = usePermission()

  const [loading, setLoading] = useState(true)
  const [config, setConfig] = useState({})
  const [cas, setCas] = useState([])
  const [stats, setStats] = useState({ total: 0, successful: 0, failed: 0 })
  const [activeTab, setActiveTab] = useState('settings')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const [configRes, casRes, statsRes] = await Promise.all([
        estService.getConfig(),
        casService.getAll(),
        estService.getStats()
      ])
      setConfig(configRes.data || {})
      setCas(casRes.data || [])
      setStats(statsRes.data || { total: 0, successful: 0, failed: 0 })
    } catch (error) {
      showError(error.message || t('messages.errors.loadFailed.est'))
    } finally {
      setLoading(false)
    }
  }

  const handleSaveConfig = async () => {
    if (!canWrite('est')) return
    setSaving(true)
    try {
      await estService.updateConfig(config)
      showSuccess(t('messages.success.update.settings'))
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.settings'))
    } finally {
      setSaving(false)
    }
  }

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text)
    showInfo(t('est.copied'))
  }

  const baseUrl = typeof window !== 'undefined' ? window.location.origin : ''

  const estEndpoints = useMemo(() => [
    { key: 'cacerts', path: '/.well-known/est/cacerts' },
    { key: 'simpleenroll', path: '/.well-known/est/simpleenroll' },
    { key: 'simplereenroll', path: '/.well-known/est/simplereenroll' },
    { key: 'csrattrs', path: '/.well-known/est/csrattrs' },
    { key: 'serverkeygen', path: '/.well-known/est/serverkeygen' },
  ], [])

  const tabs = useMemo(() => [
    { id: 'settings', label: t('est.groups.settings'), icon: Gear },
    { id: 'info', label: t('est.endpoints'), icon: Info }
  ], [t])

  const headerStats = useMemo(() => [
    { icon: ChartBar, label: t('est.totalEnrollments'), value: stats.total },
    { icon: CheckCircle, label: t('est.successfulEnrollments'), value: stats.successful, variant: 'success' },
    { icon: Warning, label: t('est.failedEnrollments'), value: stats.failed, variant: stats.failed > 0 ? 'danger' : 'default' },
  ], [stats, t])

  const helpContent = (
    <div className="p-4 space-y-4">
      <Card className="p-4 space-y-3 bg-gradient-to-br from-accent-primary-op5 to-transparent">
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <ChartBar size={16} className="text-accent-primary" />
          {t('est.stats')}
        </h3>
        <div className="grid grid-cols-3 gap-3">
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-text-primary">{stats.total}</p>
            <p className="text-xs text-text-secondary">{t('est.totalEnrollments')}</p>
          </div>
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold status-success-text">{stats.successful}</p>
            <p className="text-xs text-text-secondary">{t('est.successfulEnrollments')}</p>
          </div>
          <div className="text-center p-3 bg-bg-tertiary rounded-lg">
            <p className="text-2xl font-bold text-status-danger">{stats.failed}</p>
            <p className="text-xs text-text-secondary">{t('est.failedEnrollments')}</p>
          </div>
        </div>
      </Card>

      <div className="space-y-3">
        <HelpCard variant="info" title={t('est.aboutEst')}>
          {t('est.aboutEstDesc')}
        </HelpCard>
      </div>
    </div>
  )

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full w-full">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  return (
    <ResponsiveLayout
      title={t('est.title')}
      icon={Globe}
      subtitle={config.enabled ? t('common.enabled') : t('common.disabled')}
      tabs={tabs}
      activeTab={activeTab}
      onTabChange={setActiveTab}
      tabLayout="sidebar"
      sidebarContentClass=""
      tabGroups={[
        { labelKey: 'est.groups.management', tabs: ['settings'], color: 'icon-bg-blue' },
        { labelKey: 'est.groups.settings', tabs: ['info'], color: 'icon-bg-emerald' },
      ]}
      stats={headerStats}
      helpPageKey="est"
    >
      {/* Settings Tab */}
      {activeTab === 'settings' && (
        <div className="p-4 md:p-6 max-w-3xl mx-auto space-y-6">
          <Card className="p-4">
            <div className="flex items-start gap-4">
              <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${
                config.enabled ? 'status-success-bg' : 'bg-bg-tertiary'
              }`}>
                <Plugs size={24} className={config.enabled ? 'status-success-text' : 'text-text-tertiary'} weight="duotone" />
              </div>
              <div className="flex-1">
                <ToggleSwitch
                  checked={config.enabled || false}
                  onChange={(val) => setConfig({ ...config, enabled: val })}
                  label={t('est.enableEst')}
                  description={t('est.enableEstDesc')}
                />
              </div>
            </div>
          </Card>

          <Card className="p-4 space-y-4">
            <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
              <Gear size={16} />
              {t('est.serverSettings')}
            </h3>

            <Select
              label={t('common.issuingCA')}
              placeholder={t('common.acmeSelectCA')}
              options={cas.map(ca => ({ value: ca.id.toString(), label: ca.name || ca.subject }))}
              value={config.ca_id?.toString() || ''}
              onChange={(val) => setConfig({ ...config, ca_id: parseInt(val) })}
              disabled={!config.enabled}
            />

            <Input
              label={t('est.validityDays')}
              type="number"
              value={config.validity_days || 365}
              onChange={(e) => setConfig({ ...config, validity_days: parseInt(e.target.value) })}
              min="1"
              max="3650"
              disabled={!config.enabled}
              helperText={t('est.validityDaysHelp')}
            />
          </Card>

          <Card className="p-4 space-y-4">
            <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
              <Lock size={16} />
              {t('est.basicAuth')}
            </h3>
            <p className="text-xs text-text-secondary">{t('est.basicAuthDesc')}</p>

            <Input
              label={t('est.username')}
              value={config.username || ''}
              onChange={(e) => setConfig({ ...config, username: e.target.value })}
              disabled={!config.enabled}
            />

            <Input
              label={t('est.password')}
              type="password"
              value={config.password || ''}
              onChange={(e) => setConfig({ ...config, password: e.target.value })}
              placeholder={config.password_set ? '••••••••' : ''}
              disabled={!config.enabled}
            />
          </Card>

          {hasPermission('write:est') && (
            <div className="flex justify-end">
              <Button type="button" onClick={handleSaveConfig} disabled={saving}>
                {saving ? <LoadingSpinner size="sm" /> : <Gear size={14} />}
                {saving ? t('common.saving') : t('common.saveConfiguration')}
              </Button>
            </div>
          )}
        </div>
      )}

      {/* Endpoints / Info Tab */}
      {activeTab === 'info' && (
        <div className="p-4 md:p-6 max-w-3xl mx-auto space-y-4">
          {!config.enabled && (
            <Card className="p-4 status-warning-border status-warning-bg border">
              <div className="flex items-start gap-3">
                <Warning size={20} className="status-warning-text flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-medium status-warning-text">{t('est.estDisabled')}</p>
                  <p className="text-xs text-text-secondary">{t('est.estDisabledDesc')}</p>
                </div>
              </div>
            </Card>
          )}

          <Card className="p-4 space-y-4">
            <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
              <Globe size={16} />
              {t('est.endpoints')}
            </h3>
            <p className="text-xs text-text-secondary">{t('est.endpointsDesc')}</p>

            <div className="space-y-3">
              {estEndpoints.map(ep => (
                <div key={ep.key} className="p-3 bg-bg-tertiary rounded-lg">
                  <div className="flex items-start justify-between gap-2 mb-1">
                    <div>
                      <p className="text-sm font-medium text-text-primary">{t(`est.${ep.key}`)}</p>
                      <p className="text-xs text-text-secondary">{t(`est.${ep.key}Desc`)}</p>
                    </div>
                    <Button type="button" size="sm" variant="ghost" onClick={() => copyToClipboard(`${baseUrl}${ep.path}`)} aria-label={t('common.copy')}>
                      <Copy size={14} />
                    </Button>
                  </div>
                  <code className="text-xs font-mono text-text-primary break-all">
                    {baseUrl}{ep.path}
                  </code>
                </div>
              ))}
            </div>
          </Card>

          <Card className="p-4 space-y-4">
            <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
              <Info size={16} />
              {t('est.aboutEst')}
            </h3>
            <p className="text-sm text-text-secondary">{t('est.aboutEstDesc')}</p>
          </Card>

          <Card className="p-4 space-y-4">
            <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
              <CheckCircle size={16} />
              {t('est.stats')}
            </h3>
            {stats.total > 0 ? (
              <div className="grid grid-cols-3 gap-3">
                <div className="text-center p-3 bg-bg-tertiary rounded-lg">
                  <p className="text-2xl font-bold text-text-primary">{stats.total}</p>
                  <p className="text-xs text-text-secondary">{t('est.totalEnrollments')}</p>
                </div>
                <div className="text-center p-3 bg-bg-tertiary rounded-lg">
                  <p className="text-2xl font-bold status-success-text">{stats.successful}</p>
                  <p className="text-xs text-text-secondary">{t('est.successfulEnrollments')}</p>
                </div>
                <div className="text-center p-3 bg-bg-tertiary rounded-lg">
                  <p className="text-2xl font-bold text-status-danger">{stats.failed}</p>
                  <p className="text-xs text-text-secondary">{t('est.failedEnrollments')}</p>
                </div>
              </div>
            ) : (
              <p className="text-sm text-text-tertiary italic">{t('est.noStats')}</p>
            )}
          </Card>
        </div>
      )}
    </ResponsiveLayout>
  )
}
