/**
 * Conformance lint of a certificate in the mockup's modal(): the profiles as a `.segmented` group,
 * the count of each severity in pills, then the findings as the mockup's record list.
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { AtelierDialog, Icon, Pill, RecordList, RecordRow } from './atelier'
import { useNotification } from '../contexts'
import { certificatesService } from '../services'

const SEVERITY_TONE = { fatal: 'bad', error: 'bad', warning: 'warn', notice: 'muted', info: 'muted' }
const SEVERITY_ORDER = ['fatal', 'error', 'warning', 'notice', 'info']
const PROFILES = ['rfc5280', 'cabf', 'etsi']

export function CertificateLintModal({ certId, certName, open, onClose }) {
  if (!open) return null
  return <LintBody certId={certId} certName={certName} onClose={onClose} />
}

function LintBody({ certId, certName, onClose }) {
  const { t } = useTranslation()
  const { showError } = useNotification()
  const [profile, setProfile] = useState('rfc5280')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [available, setAvailable] = useState(true)
  const showErrorRef = useRef(showError)
  showErrorRef.current = showError
  const loadingRef = useRef(false)

  const run = useCallback(async (prof) => {
    if (loadingRef.current) return // guard: never fan out concurrent lint calls (#145)
    if (!certId) return
    loadingRef.current = true
    setLoading(true)
    try {
      const res = await certificatesService.lint(certId, prof)
      const data = res.data || res
      setResult(data)
      setAvailable(data.available !== false)
    } catch (e) {
      showErrorRef.current(e.message || t('lint.loadFailed'))
      setResult(null)
    } finally {
      loadingRef.current = false
      setLoading(false)
    }
  }, [certId, t])

  useEffect(() => { run(profile) }, [profile, run])

  const summary = result?.summary || {}
  const findings = result?.findings || []
  const about = [result?.detected_type, (result?.linters || []).join(', ')].filter(Boolean)

  return (
    <AtelierDialog title={certName ? t('lint.title', { name: certName }) : t('lint.titleGeneric')} subtitle={t('lint.subtitle')} onClose={onClose} testId="lint-dialog">
      <div className="segmented" role="group" aria-label={t('lint.profileLabel')}>
        {PROFILES.map((p) => (
          <button key={p} type="button" aria-pressed={profile === p} disabled={loading || undefined} onClick={() => setProfile(p)}>{t(`lint.profile_${p}`)}</button>
        ))}
      </div>
      <div style={{ marginTop: 18 }}>
        {loading ? (
          <p className="small muted" role="status">{t('common.loading')}</p>
        ) : !available ? (
          <div className="notice warn"><Icon name="warning" /><span>{t('lint.unavailable')}. {t('lint.unavailableHint')}</span></div>
        ) : (
          <>
            <div className="ca-badges" style={{ marginBottom: 10 }}>
              {SEVERITY_ORDER.map((s) => (summary[s] ? <Pill key={s} tone={SEVERITY_TONE[s]} label={`${summary[s]} ${t(`lint.severity.${s}`)}`} /> : null))}
              {findings.length === 0 && <Pill tone="good" label={t('lint.clean')} />}
              {about.length > 0 && <span className="small muted mono" title={result?.detected_type ? t('lint.detectedType') : undefined}>{about.join(' · ')}</span>}
            </div>
            {findings.length > 0 && (
              <RecordList>
                {findings.map((f, i) => (
                  <RecordRow key={`${f.code}-${i}`} title={<span className="mono">{f.code}</span>}
                    meta={[f.message, f.source && f.source.toUpperCase()].filter(Boolean).join(' · ')}
                    extra={f.node && <span className="rl-meta mono" title={f.node}>{f.node}</span>}
                    badge={<Pill tone={SEVERITY_TONE[f.severity] || 'muted'} label={t(`lint.severity.${f.severity}`)} />} />
                ))}
              </RecordList>
            )}
            {(profile === 'cabf' || profile === 'etsi') && findings.length > 0 && (
              <p className="small muted" style={{ marginTop: 14 }}>{profile === 'etsi' ? t('lint.etsiNote') : t('lint.cabfNote')}</p>
            )}
          </>
        )}
      </div>
      <div className="modal-actions">
        <button type="button" className="btn primary" data-action="close-modal" data-write="false" onClick={onClose}>{t('common.close')}</button>
      </div>
    </AtelierDialog>
  )
}

export default CertificateLintModal
