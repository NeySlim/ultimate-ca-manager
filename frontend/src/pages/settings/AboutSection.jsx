import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Info, HardDrives, Globe, GithubLogo, WarningCircle, Shield, Archive, Coffee,
} from '@phosphor-icons/react'
import {
  Badge, Logo, DetailContent, DetailHeader, DetailSection, DetailGrid, DetailField, Button,
} from '../../components'
import { systemService } from '../../services'
import { useNotification } from '../../contexts'
import { usePermission } from '../../hooks'
import { downloadBlob } from '../../lib/utils'
import FipsPreflightPanel from './FipsPreflightPanel'
import CompliancePreflightPanel from './CompliancePreflightPanel'
import { KOFI_URL } from '../../lib/support'

export default function AboutSection() {
  const { t } = useTranslation()
  const { showError, showSuccess } = useNotification()
  const { isAdmin, hasPermission } = usePermission()
  const [info, setInfo] = useState(null)
  const [loading, setLoading] = useState(true)
  const [bundleLoading, setBundleLoading] = useState(false)

  const handleDownloadBundle = async () => {
    setBundleLoading(true)
    try {
      const blob = await systemService.downloadLogBundle()
      // Filename from Content-Disposition if present, else fallback.
      downloadBlob(blob, `ucm-logs-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '')}.zip`)
      showSuccess(t('settings.about.logBundleSuccess'))
    } catch (error) {
      showError(error.message || t('settings.about.logBundleFailed'))
    } finally {
      setBundleLoading(false)
    }
  }

  useEffect(() => {
    const fetchInfo = async () => {
      try {
        const response = await systemService.getServiceStatus()
        setInfo(response.data)
      } catch {
        setInfo(null)
      } finally {
        setLoading(false)
      }
    }
    fetchInfo()
  }, [])

  const formatUptime = (seconds) => {
    if (!seconds) return '—'
    const d = Math.floor(seconds / 86400)
    const h = Math.floor((seconds % 86400) / 3600)
    const m = Math.floor((seconds % 3600) / 60)
    if (d > 0) return `${d}d ${h}h ${m}m`
    if (h > 0) return `${h}h ${m}m`
    return `${m}m`
  }

  return (
    <DetailContent>
      <DetailHeader
        icon={Info}
        title={t('settings.about.title')}
        subtitle={t('settings.about.subtitle')}
      />

      {/* Logo & branding */}
      <div className="flex flex-col items-center py-6 mb-4">
        <Logo variant="vertical" size="lg" />
        <div className="mt-3">
          <Badge variant="accent" size="sm">
            {loading ? '...' : `v${info?.version || __APP_VERSION__}`}
          </Badge>
        </div>
      </div>

      {/* System info */}
      <DetailSection title={t('settings.about.systemInfo')} icon={HardDrives} iconClass="icon-bg-teal">
        <DetailGrid>
          <DetailField label={t('settings.about.version')} value={info?.version || '—'} />
          <DetailField label={t('settings.about.pythonVersion')} value={info?.python_version || '—'} />
          <DetailField label={t('settings.about.uptime')} value={formatUptime(info?.uptime_seconds)} />
          <DetailField label={t('settings.about.memory')} value={info?.memory_mb ? `${info.memory_mb} MB` : '—'} />
          <DetailField label={t('settings.about.environment')} value={info?.is_docker ? 'Docker' : 'Native'} />
        </DetailGrid>
      </DetailSection>

      {/* Diagnostic bundle — admin only */}
      {isAdmin() && (
        <DetailSection title={t('settings.about.diagnostic')} icon={Archive} iconClass="icon-bg-orange" className="mt-4">
          <div className="flex items-center justify-between gap-3 p-3 bg-tertiary-50 border border-border rounded-lg">
            <div className="min-w-0">
              <div className="text-sm font-medium text-text-primary">{t('settings.about.logBundle')}</div>
              <div className="text-xs text-text-secondary">{t('settings.about.logBundleHint')}</div>
            </div>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={handleDownloadBundle}
              disabled={bundleLoading}
            >
              <Archive size={14} />
              {bundleLoading ? t('common.preparing') : t('common.download')}
            </Button>
          </div>
        </DetailSection>
      )}

      {hasPermission('admin:system') && <FipsPreflightPanel />}
      {hasPermission('admin:system') && <CompliancePreflightPanel />}

      {/* Links */}
      <DetailSection title={t('settings.about.links')} icon={Globe} iconClass="icon-bg-teal" className="mt-4">
        <div className="space-y-2">
          <a
            href="https://github.com/NeySlim/ultimate-ca-manager"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-3 p-3 bg-tertiary-50 border border-border rounded-lg hover:bg-bg-tertiary transition-colors"
          >
            <GithubLogo size={20} className="text-text-secondary" />
            <div>
              <div className="text-sm font-medium text-text-primary">GitHub</div>
              <div className="text-xs text-text-secondary">{t('settings.about.sourceCode')}</div>
            </div>
          </a>
          <a
            href="https://github.com/NeySlim/ultimate-ca-manager/issues"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-3 p-3 bg-tertiary-50 border border-border rounded-lg hover:bg-bg-tertiary transition-colors"
          >
            <WarningCircle size={20} className="text-text-secondary" />
            <div>
              <div className="text-sm font-medium text-text-primary">{t('settings.about.issues')}</div>
              <div className="text-xs text-text-secondary">{t('settings.about.reportBugs')}</div>
            </div>
          </a>
          <a
            href="https://github.com/NeySlim/ultimate-ca-manager/wiki"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-3 p-3 bg-tertiary-50 border border-border rounded-lg hover:bg-bg-tertiary transition-colors"
          >
            <Globe size={20} className="text-text-secondary" />
            <div>
              <div className="text-sm font-medium text-text-primary">{t('settings.about.documentation')}</div>
              <div className="text-xs text-text-secondary">{t('settings.about.wikiGuides')}</div>
            </div>
          </a>
          <a
            href={KOFI_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-3 p-3 bg-tertiary-50 border border-border rounded-lg hover:bg-bg-tertiary transition-colors"
          >
            <Coffee size={20} className="kofi-icon" />
            <div>
              <div className="text-sm font-medium text-text-primary">{t('settings.about.support')}</div>
              <div className="text-xs text-text-secondary">{t('settings.about.supportDesc')}</div>
            </div>
          </a>
        </div>
      </DetailSection>

      {/* License */}
      <DetailSection title={t('settings.about.license')} icon={Shield} iconClass="icon-bg-emerald" className="mt-4">
        <div className="p-3 bg-tertiary-50 border border-border rounded-lg">
          <p className="text-sm text-text-primary font-medium">GNU AGPL v3.0 only</p>
          <p className="text-xs text-text-secondary mt-1">
            © 2025-2026 Lionel Alarcon: {t('settings.about.licenseDesc')}
          </p>
        </div>
      </DetailSection>
    </DetailContent>
  )
}
