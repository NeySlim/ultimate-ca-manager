/**
 * TSA Management Page
 * Time Stamp Authority (RFC 3161) configuration and information
 */
import { useState, useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Clock, Gear, Copy, Info, Plugs, Warning, CheckCircle,
  ChartBar, Shield
} from '@phosphor-icons/react'
import {
  ResponsiveLayout,
  Button, Input, Select, Card,
  LoadingSpinner, HelpCard,
  CompactStats, FormModal
} from '../components'
import { tsaService, casService } from '../services'
import { useNotification } from '../contexts'
import { usePermission } from '../hooks'
import { ToggleSwitch } from '../components/ui/ToggleSwitch'
import { signingCas } from '../lib/caSelection'

export default function TSAPage() {
  const { t } = useTranslation()
  const { showSuccess, showError, showInfo } = useNotification()
  const { hasPermission, canWrite } = usePermission()

  const [loading, setLoading] = useState(true)
  const [config, setConfig] = useState({})
  const [cas, setCas] = useState([])
  const [signerCandidates, setSignerCandidates] = useState([])
  const [stats, setStats] = useState({ total_requests: 0 })
  const [activeTab, setActiveTab] = useState('settings')
  const [saving, setSaving] = useState(false)
  const [generateOpen, setGenerateOpen] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [genForm, setGenForm] = useState(null)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const [configRes, casRes, statsRes, candidatesRes] = await Promise.all([
        tsaService.getConfig(),
        casService.getAll(),
        tsaService.getStats(),
        tsaService.getSignerCandidates()
      ])
      setConfig(configRes.data || {})
      setCas(casRes.data || [])
      setStats(statsRes.data || { total_requests: 0 })
      setSignerCandidates(candidatesRes.data || [])
    } catch (error) {
      showError(error.message || t('messages.errors.loadFailed.tsa'))
    } finally {
      setLoading(false)
    }
  }

  const handleSaveConfig = async () => {
    if (!canWrite('settings')) return
    setSaving(true)
    try {
      await tsaService.updateConfig(config)
      showSuccess(t('messages.success.update.settings'))
      // Re-read so the resolved signer status (expiry, chain, usability)
      // reflects what was just saved and gates the strict-mode toggle.
      await loadData()
    } catch (error) {
      showError(error.message || t('messages.errors.updateFailed.settings'))
    } finally {
      setSaving(false)
    }
  }

  const openGenerate = () => {
    setGenForm({
      ca_refid: config.ca_refid || (cas[0]?.refid ?? ''),
      cn: 'UCM Timestamping Authority',
      validity_days: 397,
      key_type: 'RSA-3072',
    })
    setGenerateOpen(true)
  }

  const handleGenerateSigner = async () => {
    if (!genForm) return
    setGenerating(true)
    try {
      const kt = genForm.key_type || 'RSA-3072'
      const dash = kt.indexOf('-')
      const algo = dash === -1 ? kt : kt.slice(0, dash)
      const rest = dash === -1 ? '' : kt.slice(dash + 1)
      const res = await tsaService.issueSignerCertificate({
        ca_refid: genForm.ca_refid || undefined,
        cn: genForm.cn || undefined,
        // Send whatever the operator typed (0 included) and let the backend
        // reject it; `|| undefined` silently turned an explicit 0 into the
        // 397-day default with a success toast (#314 review).
        validity_days:
          String(genForm.validity_days ?? '').trim() === ''
            ? undefined
            : Number(genForm.validity_days),
        key_type: algo,
        key_size: algo === 'RSA' ? rest : undefined,
        curve: algo === 'EC' ? rest : undefined,
      })
      setGenerateOpen(false)
      showSuccess(
        res?.data?.selected
          ? t('tsa.signerGeneratedSelected')
          : t('tsa.signerGenerated')
      )
      await loadData()
    } catch (error) {
      showError(error.message || t('tsa.signerGenerateFailed'))
    } finally {
      setGenerating(false)
    }
  }

  // config.signer describes what is SAVED. A freshly picked certificate has
  // not been resolved yet, so only trust the status when it matches the
  // current selection.
  const signerStatus = config.signer && config.signer.refid === config.signer_cert_refid
    ? config.signer
    : null
  const selectionUnsaved = Boolean(config.signer_cert_refid) && !signerStatus

  // The strict tsa_require_dedicated_cert mode is only operable once a usable
  // dedicated signer is saved: without one, /tsa would 503 every request.
  const dedicatedSignerReady = Boolean(signerStatus?.usable)

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text)
    showInfo(t('tsa.copied'))
  }

  const baseUrl = typeof window !== 'undefined' ? window.location.origin : ''

  const tabs = useMemo(() => [
    { id: 'settings', label: t('tsa.groups.settings'), icon: Gear },
    { id: 'info', label: t('tsa.endpoint'), icon: Info }
  ], [t])

  const headerStats = useMemo(() => [
    { icon: ChartBar, label: t('tsa.totalRequests'), value: stats.total_requests },
    { icon: CheckCircle, label: t('common.status'), value: config.enabled ? t('common.enabled') : t('common.disabled'), variant: config.enabled ? 'success' : 'default' },
  ], [stats, config.enabled, t])

  const helpContent = (
    <div className="p-4 space-y-4">
      <div className="space-y-3">
        <HelpCard variant="info" title={t('tsa.aboutTsa')}>
          {t('tsa.aboutTsaDesc')}
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
      title={t('tsa.title')}
      icon={Clock}
      subtitle={config.enabled ? t('common.enabled') : t('common.disabled')}
      tabs={tabs}
      activeTab={activeTab}
      onTabChange={setActiveTab}
      tabLayout="sidebar"
      sidebarContentClass=""
      tabGroups={[
        { labelKey: 'tsa.groups.management', tabs: ['settings'], color: 'icon-bg-blue' },
        { labelKey: 'tsa.groups.info', tabs: ['info'], color: 'icon-bg-emerald' },
      ]}
      stats={headerStats}
      helpPageKey="tsa"
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
                  label={t('tsa.enableTsa')}
                  description={t('tsa.enableTsaDesc')}
                />
              </div>
            </div>
          </Card>

          <Card className="p-4 space-y-4">
            <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
              <Gear size={16} />
              {t('tsa.serverSettings')}
            </h3>

            <Select
              label={t('tsa.signingCA')}
              placeholder={t('tsa.selectCA')}
              options={signingCas(cas).map(ca => ({ value: ca.refid || ca.id.toString(), label: ca.name || ca.subject }))}
              value={config.ca_refid || ''}
              onChange={(val) => setConfig({ ...config, ca_refid: val })}
              disabled={!config.enabled}
            />

            <Input
              label={t('tsa.policyOid')}
              value={config.policy_oid || '1.2.3.4.1'}
              onChange={(e) => setConfig({ ...config, policy_oid: e.target.value })}
              disabled={!config.enabled}
              helperText={t('tsa.policyOidHelp')}
              placeholder="1.2.3.4.1"
            />
          </Card>

          <Card className="p-4 space-y-4">
            <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
              <Shield size={16} />
              {t('tsa.signingCert')}
            </h3>
            <p className="text-xs text-text-secondary">{t('tsa.signingCertDesc')}</p>

            <Select
              label={t('tsa.signingCert')}
              options={[
                { value: '', label: t('tsa.signingCertCa') },
                ...signerCandidates.map(c => ({
                  value: c.refid,
                  label: `${c.subject_cn || c.descr || c.subject}`
                    + `${c.key_type ? ` (${c.key_type})` : ''}`
                    + `${c.eku_critical_exclusive ? ` — ${t('tsa.signerStrictBadge')}` : ''}`
                }))
              ]}
              value={config.signer_cert_refid || ''}
              onChange={(val) => setConfig({
                ...config,
                signer_cert_refid: val,
                // Strict mode cannot outlive its signer: clearing or changing
                // the signer drops require_dedicated_cert so a save can never
                // persist a strict mode with no usable dedicated signer.
                ...((!val || val !== config.signer?.refid)
                  ? { require_dedicated_cert: false } : {}),
              })}
              disabled={!config.enabled}
              helperText={t('tsa.signingCertHelp')}
            />

            <div className="flex items-center justify-between gap-3">
              <p className="text-xs text-text-tertiary">{t('tsa.signerGenerateHint')}</p>
              <Button
                type="button"
                size="sm"
                variant={dedicatedSignerReady ? 'ghost' : 'secondary'}
                onClick={openGenerate}
                disabled={
                  !config.enabled
                  || !hasPermission('write:settings')
                  || !hasPermission('write:certificates')
                }
              >
                <Shield size={14} />
                {t('tsa.signerGenerate')}
              </Button>
            </div>

            {selectionUnsaved && (
              <div className="p-3 rounded-lg text-xs border border-border bg-bg-tertiary">
                <div className="flex items-start gap-2">
                  <Info size={16} className="text-text-tertiary flex-shrink-0 mt-0.5" />
                  <p className="text-text-secondary">{t('tsa.signerUnsaved')}</p>
                </div>
              </div>
            )}

            {signerStatus && (
              <div className={`p-3 rounded-lg text-xs border ${
                signerStatus.usable
                  ? 'status-success-bg status-success-border'
                  : 'status-warning-bg status-warning-border'
              }`}>
                <div className="flex items-start gap-2">
                  {signerStatus.usable
                    ? <CheckCircle size={16} className="status-success-text flex-shrink-0 mt-0.5" />
                    : <Warning size={16} className="status-warning-text flex-shrink-0 mt-0.5" />}
                  <div className="space-y-0.5">
                    {signerStatus.subject && (
                      <p className="text-text-primary font-mono break-all">{signerStatus.subject}</p>
                    )}
                    {signerStatus.not_after && (
                      <p className="text-text-secondary">
                        {t('tsa.signerExpires')}: {new Date(signerStatus.not_after).toLocaleString()}
                      </p>
                    )}
                    {signerStatus.usable ? (
                      <>
                        <p className="text-text-secondary">
                          {signerStatus.chain_to_root
                            ? t('tsa.signerChainComplete')
                            : t('tsa.signerChainPartial', { count: signerStatus.chain_len || 0 })}
                        </p>
                        <p className="text-text-secondary">
                          {signerStatus.eku_critical_exclusive
                            ? t('tsa.signerEkuStrict')
                            : t('tsa.signerEkuLoose')}
                        </p>
                      </>
                    ) : (
                      <p className="status-warning-text">
                        {signerStatus.error || t('tsa.signerUnusable')}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            )}

            <ToggleSwitch
              checked={config.require_dedicated_cert || false}
              onChange={(val) => setConfig({ ...config, require_dedicated_cert: val })}
              label={t('tsa.requireDedicatedCert')}
              description={
                dedicatedSignerReady
                  ? t('tsa.requireDedicatedCertDesc')
                  : t('tsa.requireDedicatedCertBlocked')
              }
              disabled={!config.enabled || (!dedicatedSignerReady && !config.require_dedicated_cert)}
            />
          </Card>

          {hasPermission('write:settings') && (
            <div className="flex justify-end">
              <Button type="button" onClick={handleSaveConfig} disabled={saving}>
                {saving ? <LoadingSpinner size="sm" /> : <Gear size={14} />}
                {saving ? t('common.saving') : t('common.saveConfiguration')}
              </Button>
            </div>
          )}

          {generateOpen && genForm && (
            <FormModal
              open={generateOpen}
              onClose={() => setGenerateOpen(false)}
              title={t('tsa.signerGenerateTitle')}
              onSubmit={handleGenerateSigner}
              submitLabel={t('tsa.signerGenerate')}
              loading={generating}
            >
              <p className="text-xs text-text-secondary">{t('tsa.signerGenerateModalDesc')}</p>
              <Select
                label={t('tsa.signingCA')}
                options={signingCas(cas).map(ca => ({
                  value: ca.refid || ca.id.toString(),
                  label: ca.name || ca.subject,
                }))}
                value={genForm.ca_refid}
                onChange={(val) => setGenForm({ ...genForm, ca_refid: val })}
              />
              <Input
                label={t('tsa.signerGenerateCn')}
                value={genForm.cn}
                onChange={(e) => setGenForm({ ...genForm, cn: e.target.value })}
              />
              <Input
                label={t('tsa.signerGenerateValidity')}
                type="number"
                value={genForm.validity_days}
                onChange={(e) => setGenForm({ ...genForm, validity_days: e.target.value })}
              />
              <Select
                label={t('tsa.signerGenerateKeyType')}
                options={[
                  { value: 'RSA-3072', label: 'RSA 3072' },
                  { value: 'RSA-2048', label: 'RSA 2048' },
                  { value: 'RSA-4096', label: 'RSA 4096' },
                  { value: 'EC-P-256', label: 'EC P-256' },
                  { value: 'EC-P-384', label: 'EC P-384' },
                ]}
                value={genForm.key_type}
                onChange={(val) => setGenForm({ ...genForm, key_type: val })}
              />
              <p className="text-xs text-text-tertiary">{t('tsa.signerGenerateRenewalNote')}</p>
            </FormModal>
          )}
        </div>
      )}

      {/* Endpoint / Info Tab */}
      {activeTab === 'info' && (
        <div className="p-4 md:p-6 max-w-3xl mx-auto space-y-4">
          {!config.enabled && (
            <Card className="p-4 status-warning-border status-warning-bg border">
              <div className="flex items-start gap-3">
                <Warning size={20} className="status-warning-text flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-medium status-warning-text">{t('tsa.tsaDisabled')}</p>
                  <p className="text-xs text-text-secondary">{t('tsa.tsaDisabledDesc')}</p>
                </div>
              </div>
            </Card>
          )}

          <Card className="p-4 space-y-4">
            <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
              <Clock size={16} />
              {t('tsa.endpoint')}
            </h3>
            <p className="text-xs text-text-secondary">{t('tsa.endpointDesc')}</p>

            <div className="p-3 bg-bg-tertiary rounded-lg">
              <div className="flex items-start justify-between gap-2 mb-1">
                <div>
                  <p className="text-sm font-medium text-text-primary">{t('tsa.timestampRequest')}</p>
                  <p className="text-xs text-text-secondary">POST application/timestamp-query</p>
                </div>
                <Button type="button" size="sm" variant="ghost" onClick={() => copyToClipboard(`${baseUrl}/tsa`)}>
                  <Copy size={14} />
                </Button>
              </div>
              <code className="text-xs font-mono text-text-primary break-all">
                {baseUrl}/tsa
              </code>
            </div>
          </Card>

          <Card className="p-4 space-y-4">
            <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
              <Shield size={16} />
              {t('tsa.usage')}
            </h3>
            <div className="space-y-3">
              <div className="p-3 bg-bg-tertiary rounded-lg">
                <p className="text-xs font-medium text-text-primary mb-2">{t('tsa.usageCreateRequest')}</p>
                <code className="text-xs font-mono text-text-secondary break-all block">
                  openssl ts -query -data file.pdf -sha256 -out request.tsq
                </code>
              </div>
              <div className="p-3 bg-bg-tertiary rounded-lg">
                <p className="text-xs font-medium text-text-primary mb-2">{t('tsa.usageSendRequest')}</p>
                <code className="text-xs font-mono text-text-secondary break-all block">
                  {`curl -X POST -H "Content-Type: application/timestamp-query" --data-binary @request.tsq ${baseUrl}/tsa -o response.tsr`}
                </code>
              </div>
              <div className="p-3 bg-bg-tertiary rounded-lg">
                <p className="text-xs font-medium text-text-primary mb-2">{t('tsa.usageVerify')}</p>
                <code className="text-xs font-mono text-text-secondary break-all block">
                  openssl ts -reply -in response.tsr -text
                </code>
              </div>
            </div>
          </Card>

          <Card className="p-4 space-y-4">
            <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
              <Info size={16} />
              {t('tsa.aboutTsa')}
            </h3>
            <p className="text-sm text-text-secondary">{t('tsa.aboutTsaDesc')}</p>
          </Card>
        </div>
      )}
    </ResponsiveLayout>
  )
}
