import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ShieldCheck, Question, WarningCircle } from '@phosphor-icons/react'
import { Button } from '../../components'
import PreflightReport from '../../components/PreflightReport'
import { systemService } from '../../services'
import { FormGroup } from '../../components/sectioned'
import { useRefocusAfter } from '../../components/sectioned/useRefocus'

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

  return (
    <FormGroup title={t('settings.fipsPreflight.title')}>
      <div className="space-y-3">
        {/* The check as the mockup's test zone: the button, its hint or its failure beside it */}
        <div className="sf-test">
          <Button ref={runRef} type="button" variant="secondary" onClick={runCheck} disabled={loading}>
            <ShieldCheck size={16} />
            {loading ? t('settings.fipsPreflight.running') : t('settings.fipsPreflight.run')}
          </Button>
          <p className={error ? 'sf-test-result is-bad' : 'sf-test-result'} role={error ? 'alert' : undefined}>
            {error ? <WarningCircle aria-hidden="true" /> : <Question aria-hidden="true" />}
            <span>{error || t('settings.fipsPreflight.hint')}</span>
          </p>
        </div>

        {report?.module_known === false && (
          <p className="sf-hint">{t('settings.fipsPreflight.withoutModule')}</p>
        )}

        {report && <PreflightReport report={report} testId="fips-preflight-report" checkBase="settings.fipsPreflight.checks" />}
      </div>
    </FormGroup>
  )
}
