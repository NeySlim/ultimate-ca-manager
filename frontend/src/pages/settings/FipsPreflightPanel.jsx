import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ShieldCheck } from '@phosphor-icons/react'
import { Button, DetailSection } from '../../components'
import PreflightReport from '../../components/PreflightReport'
import { systemService } from '../../services'

export default function FipsPreflightPanel() {
  const { t } = useTranslation()
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

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
    <DetailSection title={t('settings.fipsPreflight.title')} icon={ShieldCheck} iconClass="icon-bg-violet" className="mt-4">
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-3 p-3 bg-tertiary-50 border border-border rounded-lg">
          <div className="min-w-0 text-xs text-text-secondary">{t('settings.fipsPreflight.hint')}</div>
          <Button type="button" size="sm" variant="secondary" onClick={runCheck} disabled={loading}>
            <ShieldCheck size={14} />
            {loading ? t('settings.fipsPreflight.running') : t('settings.fipsPreflight.run')}
          </Button>
        </div>

        {error && <p className="text-sm status-danger-text">{error}</p>}

        {report && <PreflightReport report={report} testId="fips-preflight-report" checkBase="settings.fipsPreflight.checks" />}
      </div>
    </DetailSection>
  )
}
