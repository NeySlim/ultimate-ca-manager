import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import PreflightReport from '../../components/PreflightReport'
import { systemService } from '../../services'
import { SettingsGroup, SettingsTest } from '../../components/atelier/SettingsView'
import { useRefocusAfter } from '../../hooks/useRefocus'

export default function FipsPreflightPanel() {
  const { t } = useTranslation()
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const runRef = useRef(null)
  useRefocusAfter(loading, runRef)

  const runCheck = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await systemService.getFipsPreflight()
      setReport(response.data)
    } catch (err) {
      setReport(null)
      setError(err.message || t('settings.fipsPreflight.failed'))
    } finally {
      setLoading(false)
    }
  }

  // The check as the mockup's test zone: the button, its hint or its failure beside it, the report under it
  return (
    <SettingsGroup legend={t('settings.fipsPreflight.title')} grid={false}>
      <SettingsTest id="fips-preflight" icon="shield" label={loading ? t('settings.fipsPreflight.running') : t('settings.fipsPreflight.run')}
        onTest={runCheck} busy={loading} buttonRef={runRef} write={false}
        result={error ? { ok: false, text: error } : null} hint={t('settings.fipsPreflight.hint')} />
      {report?.module_known === false && <p className="group-hint">{t('settings.fipsPreflight.withoutModule')}</p>}
      {report && <PreflightReport report={report} testId="fips-preflight-report" checkBase="settings.fipsPreflight.checks" />}
    </SettingsGroup>
  )
}
