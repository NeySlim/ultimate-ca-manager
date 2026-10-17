import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ShieldCheck } from '@phosphor-icons/react'
import { Badge, Button, DetailSection } from '../../components'
import { systemService } from '../../services'

const SEVERITIES = [
  { id: 'blocker', variant: 'danger' },
  { id: 'warning', variant: 'warning' },
  { id: 'info', variant: 'info' },
]

// i18n keys cannot hold dots inside a segment: 'users.password_scrypt' -> 'users_password_scrypt'
const checkKey = (id) => `settings.fipsPreflight.checks.${id.replace(/\./g, '_')}`

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

        {report && (
          <div className="space-y-3" data-testid="fips-preflight-report">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={report.ready ? 'success' : 'danger'}>
                {report.ready ? t('settings.fipsPreflight.ready') : t('settings.fipsPreflight.notReady')}
              </Badge>
              {SEVERITIES.map(({ id, variant }) => (
                <Badge key={id} variant={variant}>
                  {t(`settings.fipsPreflight.severity.${id}`)}: {report.summary?.[id] ?? 0}
                </Badge>
              ))}
            </div>

            {report.findings.length === 0 && report.errors.length === 0 && (
              <p className="text-sm text-text-secondary">{t('settings.fipsPreflight.nothingFound')}</p>
            )}

            {SEVERITIES.map(({ id: severity, variant }) => {
              const findings = report.findings.filter((f) => f.severity === severity)
              if (findings.length === 0) return null
              return (
                <div key={severity} className="space-y-2">
                  <h4 className="text-xs font-semibold uppercase text-text-secondary">
                    {t(`settings.fipsPreflight.severity.${severity}`)}
                  </h4>
                  {findings.map((finding) => (
                    <div key={finding.id} className="p-3 bg-tertiary-50 border border-border rounded-lg">
                      <div className="flex items-start justify-between gap-2">
                        <div className="text-sm font-medium text-text-primary">
                          {t(`${checkKey(finding.id)}.title`, { defaultValue: finding.title })}
                        </div>
                        <Badge variant={variant} size="sm">{finding.count}</Badge>
                      </div>
                      <div className="text-xs text-text-tertiary font-mono mt-1">{finding.id}</div>
                      <ul className="mt-2 text-xs text-text-secondary list-disc pl-4">
                        {finding.examples.map((example) => <li key={example}>{example}</li>)}
                        {finding.count > finding.examples.length && (
                          <li>{t('settings.fipsPreflight.more', { count: finding.count - finding.examples.length })}</li>
                        )}
                      </ul>
                      <div className="mt-2 text-xs text-text-primary">
                        <span className="font-medium">{t('settings.fipsPreflight.remedy')}</span>{' '}
                        {t(`${checkKey(finding.id)}.remedy`, { defaultValue: finding.remedy })}
                      </div>
                    </div>
                  ))}
                </div>
              )
            })}

            {report.errors.map((item) => (
              <p key={item.id} className="text-xs status-danger-text">
                {t('settings.fipsPreflight.checkFailed', { id: item.id })}
              </p>
            ))}
          </div>
        )}
      </div>
    </DetailSection>
  )
}
