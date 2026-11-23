import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Btn, Facts, RecordList, RecordRow } from '../../components/atelier'
import { SettingsGroup } from '../../components/atelier/SettingsView'
import { systemService } from '../../services'
import { useNotification } from '../../contexts'
import { usePermission } from '../../hooks'
import { downloadBlob } from '../../lib/utils'
import { formatBytes } from '../../lib/fileSize'
import { compactAgo } from '../../lib/relativeTime'
import FipsPreflightPanel from './FipsPreflightPanel'
import CompliancePreflightPanel from './CompliancePreflightPanel'
import { KOFI_URL } from '../../lib/support'
import { fact } from '../../components/atelier/facts'

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
    : null
  const links = [
    { href: REPO, title: 'GitHub', meta: t('settings.about.sourceCode') },
    { href: `${REPO}/issues`, title: t('settings.about.issues'), meta: t('settings.about.reportBugs') },
    { href: `${REPO}/wiki`, title: t('settings.about.documentation'), meta: t('settings.about.wikiGuides') },
    { href: KOFI_URL, title: t('settings.about.support'), meta: t('settings.about.supportDesc') },
  ]

  return (
    <>
      <SettingsGroup legend={t('settings.about.systemInfo')} grid={false}>
        <Facts items={[
          [t('settings.about.version'), info?.version || __APP_VERSION__],
          fact(t('settings.about.pythonVersion'), info?.python_version),
          fact(t('settings.about.started'), started),
          fact(t('settings.about.memory'), info?.memory_mb ? formatBytes(info.memory_mb * 1024 * 1024, i18n?.language) : null),
          fact(t('settings.about.environment'), info ? (info.is_docker ? 'Docker' : t('settings.about.envNative')) : null),
        ]} />
      </SettingsGroup>

      {/* Diagnostic bundle: admin only */}
      {isAdmin() && (
        <SettingsGroup legend={t('settings.about.diagnostic')} grid={false}>
          <RecordList>
            <RecordRow title={t('settings.about.logBundle')} meta={t('settings.about.logBundleHint')}
              action={(
                <Btn icon="archive" onClick={handleDownloadBundle} disabled={bundleLoading}>
                  {bundleLoading ? t('common.preparing') : t('common.download')}
                </Btn>
              )} />
          </RecordList>
        </SettingsGroup>
      )}

      <SettingsGroup legend={t('settings.about.links')} grid={false}>
        <RecordList>
          {links.map((link) => (
            <RecordRow key={link.href} meta={link.meta}
              title={<a className="text-link" href={link.href} target="_blank" rel="noopener noreferrer">{link.title}</a>} />
          ))}
        </RecordList>
      </SettingsGroup>

      <SettingsGroup legend={t('settings.about.license')} grid={false}>
        <RecordList>
          <RecordRow title="GNU AGPL v3.0 only" meta={`© 2025-2026 Lionel Alarcon: ${t('settings.about.licenseDesc')}`} />
        </RecordList>
      </SettingsGroup>

      {/* The checks last, as the mockup ends a frame with its test */}
      {hasPermission('admin:system') && <FipsPreflightPanel />}
      {(hasPermission('admin:system') || hasPermission('admin:settings')) && <CompliancePreflightPanel />}
    </>
  )
}
