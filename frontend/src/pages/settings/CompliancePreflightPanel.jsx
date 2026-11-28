import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Select } from '../../components/atelier/Form'
import { SettingsGroup, SettingsTest } from '../../components/atelier/SettingsView'
import PreflightReport from '../../components/PreflightReport'
import { settingsService, systemService } from '../../services'
import { useNotification } from '../../contexts'
import { usePermission } from '../../hooks'
import { extractData } from '../../lib/utils'
import { COMPLIANCE_PROFILE_NAMES, useComplianceProfiles } from '../../lib/complianceProfiles'

const VERDICT = {
  ready: 'settings.compliancePreflight.ready',
  notReady: 'settings.compliancePreflight.notReady',
  nothingFound: 'settings.compliancePreflight.nothingFound',
}

export default function CompliancePreflightPanel() {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  const { hasPermission } = usePermission()
  const canSetDefault = hasPermission('admin:settings')
  const canCheck = hasPermission('admin:system')
  const profiles = useComplianceProfiles()
  const options = COMPLIANCE_PROFILE_NAMES.map((n) => ({
    value: n, label: profiles[n] ? `${profiles[n].title} (${profiles[n].reference})` : n,
  }))

  const [defaultProfile, setDefaultProfile] = useState('')
  const [savingDefault, setSavingDefault] = useState(false)
  const [profile, setProfile] = useState(COMPLIANCE_PROFILE_NAMES[0])
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    Promise.resolve()
      .then(() => settingsService.getAll({ reuse: true }))
      .then((res) => {
        const name = (extractData(res) || {}).compliance_profile_default
        if (!cancelled && COMPLIANCE_PROFILE_NAMES.includes(name)) setDefaultProfile(name)
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [])

  const saveDefault = async (value) => {
    setSavingDefault(true)
    try {
      await settingsService.updateBulk({ compliance_profile_default: value })
      setDefaultProfile(value)
      showSuccess(t('settings.compliancePreflight.defaultSaved'))
    } catch (err) {
      showError(err?.message || t('settings.compliancePreflight.defaultFailed'))
    } finally {
      setSavingDefault(false)
    }
  }

  const runCheck = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await systemService.getCompliancePreflight(profile)
      setReport(response.data)
    } catch (err) {
      setReport(null)
      setError(err.message || t('settings.compliancePreflight.failed'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <SettingsGroup legend={t('settings.compliancePreflight.title')} grid={false}>
      <div className="settings-grid">
        <Select id="set-compliance_profile_default" label={t('settings.compliancePreflight.defaultProfile')}
          options={[{ value: '', label: t('cas.complianceProfileNone') }, ...options]} value={defaultProfile} onChange={saveDefault}
          disabled={!canSetDefault || savingDefault} hint={t('settings.compliancePreflight.defaultHint')} />
      </div>
      {/* The check as the mockup's test zone: the profile, then the button on its line */}
      {canCheck && (
        <SettingsTest id="compliance-preflight" icon="shield" onTest={runCheck} busy={loading} write={false}
          label={loading ? t('settings.compliancePreflight.running') : t('settings.compliancePreflight.run')}
          result={error ? { ok: false, text: error } : null} hint={t('settings.compliancePreflight.hint')}>
          <Select id="set-compliance_profile" label={t('settings.compliancePreflight.profile')} options={options} value={profile}
            onChange={(value) => { setProfile(value); setReport(null) }} />
        </SettingsTest>
      )}
      {report && <PreflightReport report={report} testId="compliance-preflight-report" verdict={VERDICT} />}
    </SettingsGroup>
  )
}
