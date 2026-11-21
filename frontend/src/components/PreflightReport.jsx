import { useTranslation } from 'react-i18next'
import { Icon, Pill, RecordList, RecordRow } from './atelier'
import { Notice } from './atelier/Form'

// The tone of each severity in the mockup's pills
const SEVERITIES = [
  { id: 'blocker', tone: 'bad' },
  { id: 'warning', tone: 'warn' },
  { id: 'info', tone: 'muted' },
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

const TONE = { blocker: 'bad', warning: 'warn', info: 'muted' }

export default function PreflightReport({ report, testId, checkBase = null, verdict = FIPS_VERDICT, atelier = false }) {
  const { t } = useTranslation()
  const checkText = (finding, part) => checkBase
    ? t(`${checkKey(checkBase, finding.id)}.${part}`, { defaultValue: finding[part] })
    : finding[part]
  if (atelier) return <AtelierReport report={report} testId={testId} verdict={verdict} checkText={checkText} t={t} />

  return (
    <div className="settings-stack" data-testid={testId}>
      <div className="settings-actions">
        <Pill tone={report.ready ? 'good' : 'bad'} label={report.ready ? t(verdict.ready) : t(verdict.notReady)} />
        {SEVERITIES.map(({ id, tone }) => (
          <Pill key={id} tone={tone} label={`${t(`settings.fipsPreflight.severity.${id}`)}: ${report.summary?.[id] ?? 0}`} />
        ))}
      </div>

      {report.findings.length === 0 && report.errors.length === 0 && (
        <p className="muted small">{t(verdict.nothingFound)}</p>
      )}

      {SEVERITIES.map(({ id: severity, tone }) => {
        const findings = report.findings.filter((f) => f.severity === severity)
        if (findings.length === 0) return null
        return (
          <section key={severity}>
            <h3 className="section-title">{t(`settings.fipsPreflight.severity.${severity}`)}</h3>
            <RecordList>
              {findings.map((finding) => (
                <RecordRow key={finding.id} title={checkText(finding, 'title')} meta={<span className="mono">{finding.id}</span>}
                  badge={<Pill tone={tone} label={String(finding.count)} />}
                  extra={(
                    <>
                      <ul className="preflight-examples">
                        {finding.examples.map((example) => <li key={example}>{example}</li>)}
                        {finding.count > finding.examples.length && (
                          <li>{t('settings.fipsPreflight.more', { count: finding.count - finding.examples.length })}</li>
                        )}
                      </ul>
                      <span className="rl-meta"><strong>{t('settings.fipsPreflight.remedy')}</strong>{' '}{checkText(finding, 'remedy')}</span>
                    </>
                  )} />
              ))}
            </RecordList>
          </section>
        )
      })}

      {report.errors.map((item) => (
        <Notice key={item.id} tone="bad">{t('settings.fipsPreflight.checkFailed', { id: item.id })}</Notice>
      ))}
    </div>
  )
}

// Inside a dialog of the mockup: the verdict and counts as pills, each severity a titled record list
function AtelierReport({ report, testId, verdict, checkText, t }) {
  return (
    <div data-testid={testId}>
      <div className="ca-badges">
        <Pill tone={report.ready ? 'good' : 'bad'} label={report.ready ? t(verdict.ready) : t(verdict.notReady)} />
        {SEVERITIES.map(({ id }) => (
          <Pill key={id} tone={TONE[id]} label={`${t(`settings.fipsPreflight.severity.${id}`)}: ${report.summary?.[id] ?? 0}`} />
        ))}
      </div>
      {report.findings.length === 0 && report.errors.length === 0 && (
        <p className="small muted" style={{ marginTop: 12 }}>{t(verdict.nothingFound)}</p>
      )}
      {SEVERITIES.map(({ id: severity }) => {
        const findings = report.findings.filter((f) => f.severity === severity)
        if (findings.length === 0) return null
        return (
          <section key={severity} style={{ marginTop: 16 }}>
            <h3 className="section-title">{t(`settings.fipsPreflight.severity.${severity}`)}</h3>
            <RecordList>
              {findings.map((finding) => (
                <RecordRow key={finding.id} title={checkText(finding, 'title')} meta={<span className="mono">{finding.id}</span>}
                  badge={<Pill tone={TONE[severity]} label={String(finding.count)} />}
                  extra={(
                    <>
                      <ul className="rl-meta" style={{ margin: '4px 0 0', paddingLeft: 17 }}>
                        {finding.examples.map((example) => <li key={example}>{example}</li>)}
                        {finding.count > finding.examples.length && (
                          <li>{t('settings.fipsPreflight.more', { count: finding.count - finding.examples.length })}</li>
                        )}
                      </ul>
                      <span className="rl-meta"><strong>{t('settings.fipsPreflight.remedy')}</strong> {checkText(finding, 'remedy')}</span>
                    </>
                  )} />
              ))}
            </RecordList>
          </section>
        )
      })}
      {report.errors.map((item) => (
        <p key={item.id} className="field-error" style={{ marginTop: 8 }}><Icon name="warning" /><span>{t('settings.fipsPreflight.checkFailed', { id: item.id })}</span></p>
      ))}
    </div>
  )
}
