import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ShieldCheck, Question } from '@phosphor-icons/react'
import { Button, Select } from '../../components'
import PreflightReport from '../../components/PreflightReport'
import { settingsService, systemService } from '../../services'
import { useNotification } from '../../contexts'
import { usePermission } from '../../hooks'
import { extractData } from '../../lib/utils'
import { COMPLIANCE_PROFILE_NAMES, useComplianceProfiles } from '../../lib/complianceProfiles'
import { FormGroup } from '../../components/sectioned'

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
    <FormGroup title={t('settings.compliancePreflight.title')} className="mt-4">
      <div className="space-y-3">
        <Select
          label={t('settings.compliancePreflight.defaultProfile')}
          options={[{ value: '', label: t('cas.complianceProfileNone') }, ...options]}
          value={defaultProfile}
          onChange={saveDefault}
          disabled={!canSetDefault || savingDefault}
          helperText={t('settings.compliancePreflight.defaultHint')}
        />

        {/* The check as the mockup's test zone: the profile, then the button on its line */}
        {canCheck && <div className="sf-test sf-wide">
          <div className="sf-test-field">
            <Select
              label={t('settings.compliancePreflight.profile')}
              options={options}
              value={profile}
              onChange={(value) => { setProfile(value); setReport(null) }}
            />
          </div>
          <Button type="button" variant="secondary" onClick={runCheck} disabled={loading}>
            <ShieldCheck size={16} />
            {loading ? t('settings.compliancePreflight.running') : t('settings.compliancePreflight.run')}
          </Button>
          <p className="sf-test-result">
            <Question aria-hidden="true" />
            <span>{t('settings.compliancePreflight.hint')}</span>
          </p>
        </div>}

        {error && <p className="ui-error sf-wide" role="alert">{error}</p>}

        {report && <PreflightReport report={report} testId="compliance-preflight-report" verdict={VERDICT} />}
      </div>
    </FormGroup>
  )
}
