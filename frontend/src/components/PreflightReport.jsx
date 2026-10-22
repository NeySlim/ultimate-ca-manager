import { useTranslation } from 'react-i18next'
import { Badge } from './Badge'

const SEVERITIES = [
  { id: 'blocker', variant: 'danger' },
  { id: 'warning', variant: 'warning' },
  { id: 'info', variant: 'info' },
]

// i18n keys cannot hold dots inside a segment: 'users.password_scrypt' -> 'users_password_scrypt'
const checkKey = (base, id) => `${base}.${id.replace(/\./g, '_')}`

/**
 * Findings of a preflight report grouped by severity. With `checkBase` the
 * title and remedy of a check come from i18n; without it, from the server text.
 * `verdict` names the three keys that word the outcome.
 */
const FIPS_VERDICT = {
  ready: 'settings.fipsPreflight.ready',
  notReady: 'settings.fipsPreflight.notReady',
  nothingFound: 'settings.fipsPreflight.nothingFound',
}

export default function PreflightReport({ report, testId, checkBase = null, verdict = FIPS_VERDICT }) {
  const { t } = useTranslation()
  const checkText = (finding, part) => checkBase
    ? t(`${checkKey(checkBase, finding.id)}.${part}`, { defaultValue: finding[part] })
    : finding[part]

  return (
    <div className="space-y-3" data-testid={testId}>
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={report.ready ? 'success' : 'danger'}>
          {report.ready ? t(verdict.ready) : t(verdict.notReady)}
        </Badge>
        {SEVERITIES.map(({ id, variant }) => (
          <Badge key={id} variant={variant}>
            {t(`settings.fipsPreflight.severity.${id}`)}: {report.summary?.[id] ?? 0}
          </Badge>
        ))}
      </div>

      {report.findings.length === 0 && report.errors.length === 0 && (
        <p className="text-sm text-text-secondary">{t(verdict.nothingFound)}</p>
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
                    {checkText(finding, 'title')}
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
                  {checkText(finding, 'remedy')}
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
  )
}
