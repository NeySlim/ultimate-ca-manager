import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Archive } from '@phosphor-icons/react'
import { Button } from '../../components'
import { systemService } from '../../services'
import { useNotification } from '../../contexts'
import { usePermission } from '../../hooks'
import { downloadBlob } from '../../lib/utils'
import { formatBytes } from '../../lib/fileSize'
import { compactAgo } from '../../lib/relativeTime'
import FipsPreflightPanel from './FipsPreflightPanel'
import CompliancePreflightPanel from './CompliancePreflightPanel'
import { KOFI_URL } from '../../lib/support'
import { FormGroup, FormProps } from '../../components/sectioned'

const REPO = 'https://github.com/NeySlim/ultimate-ca-manager'

export default function AboutSection() {
  const { t, i18n } = useTranslation()
  const { showError, showSuccess } = useNotification()
  const { isAdmin, hasPermission } = usePermission()
  const [info, setInfo] = useState(null)
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
      }
    }
    fetchInfo()
  }, [])

  // The start of the service worded as the mockup words a past event (« il y a 19 h »)
  const started = info?.uptime_seconds
    ? compactAgo(new Date(Date.now() - info.uptime_seconds * 1000), t)
    : '—'
  const links = [
    { href: REPO, title: 'GitHub', meta: t('settings.about.sourceCode') },
    { href: `${REPO}/issues`, title: t('settings.about.issues'), meta: t('settings.about.reportBugs') },
    { href: `${REPO}/wiki`, title: t('settings.about.documentation'), meta: t('settings.about.wikiGuides') },
    { href: KOFI_URL, title: t('settings.about.support'), meta: t('settings.about.supportDesc') },
  ]

  return (
    <>
      <FormGroup title={t('settings.about.systemInfo')}>
        <FormProps items={[
          [t('settings.about.version'), info?.version || __APP_VERSION__],
          [t('settings.about.pythonVersion'), info?.python_version || '—'],
          [t('settings.about.started'), started],
          [t('settings.about.memory'), info?.memory_mb ? formatBytes(info.memory_mb * 1024 * 1024, i18n?.language) : '—'],
          [t('settings.about.environment'), info ? (info.is_docker ? 'Docker' : t('settings.about.envNative')) : '—'],
        ]} />
      </FormGroup>

      {/* Diagnostic bundle: admin only */}
      {isAdmin() && (
        <FormGroup title={t('settings.about.diagnostic')}>
          <ul className="sf-records">
            <li>
              <div className="sf-record-main">
                <strong>{t('settings.about.logBundle')}</strong>
                <span className="sf-record-meta">{t('settings.about.logBundleHint')}</span>
              </div>
              <div className="sf-record-actions">
                <Button type="button" variant="secondary" onClick={handleDownloadBundle} disabled={bundleLoading}>
                  <Archive size={16} />
                  {bundleLoading ? t('common.preparing') : t('common.download')}
                </Button>
              </div>
            </li>
          </ul>
        </FormGroup>
      )}

      <FormGroup title={t('settings.about.links')}>
        <ul className="sf-records">
          {links.map((link) => (
            <li key={link.href}>
              <div className="sf-record-main">
                <strong><a className="sf-link" href={link.href} target="_blank" rel="noopener noreferrer">{link.title}</a></strong>
                <span className="sf-record-meta">{link.meta}</span>
              </div>
            </li>
          ))}
        </ul>
      </FormGroup>

      <FormGroup title={t('settings.about.license')}>
        <ul className="sf-records">
          <li>
            <div className="sf-record-main">
              <strong>GNU AGPL v3.0 only</strong>
              <span className="sf-record-meta">© 2025-2026 Lionel Alarcon: {t('settings.about.licenseDesc')}</span>
            </div>
          </li>
        </ul>
      </FormGroup>

      {/* The checks last, as the mockup ends a frame with its test */}
      {hasPermission('admin:system') && <FipsPreflightPanel />}
      {(hasPermission('admin:system') || hasPermission('admin:settings')) && <CompliancePreflightPanel />}
    </>
  )
}
