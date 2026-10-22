import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ShieldCheck } from '@phosphor-icons/react'
import { Button, DetailSection, Select } from '../../components'
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
      .then(() => settingsService.getAll())
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
    <DetailSection title={t('settings.compliancePreflight.title')} icon={ShieldCheck} iconClass="icon-bg-violet" className="mt-4">
      <div className="space-y-3">
        <div className="p-3 bg-tertiary-50 border border-border rounded-lg space-y-2">
          <Select
            label={t('settings.compliancePreflight.defaultProfile')}
            options={[{ value: '', label: t('cas.complianceProfileNone') }, ...options]}
            value={defaultProfile}
            onChange={saveDefault}
            disabled={!canSetDefault || savingDefault}
            helperText={t('settings.compliancePreflight.defaultHint')}
          />
        </div>

        <div className="flex items-end justify-between gap-3 p-3 bg-tertiary-50 border border-border rounded-lg">
          <div className="min-w-0 flex-1 space-y-1">
            <Select
              label={t('settings.compliancePreflight.profile')}
              options={options}
              value={profile}
              onChange={(value) => { setProfile(value); setReport(null) }}
              helperText={t('settings.compliancePreflight.hint')}
            />
          </div>
          <Button type="button" size="sm" variant="secondary" onClick={runCheck} disabled={loading}>
            <ShieldCheck size={14} />
            {loading ? t('settings.compliancePreflight.running') : t('settings.compliancePreflight.run')}
          </Button>
        </div>

        {error && <p className="text-sm status-danger-text">{error}</p>}

        {report && <PreflightReport report={report} testId="compliance-preflight-report" verdict={VERDICT} />}
      </div>
    </DetailSection>
  )
}
