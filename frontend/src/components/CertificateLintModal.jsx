import { useState, useEffect, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { ShieldCheck, ShieldWarning, CheckCircle, Warning } from '@phosphor-icons/react'
import { Modal } from './Modal'
import { Button } from './Button'
import { Badge } from './Badge'
import { useNotification } from '../contexts'
import { certificatesService } from '../services'

const SEVERITY_VARIANT = {
  fatal: 'danger',
  error: 'danger',
  warning: 'warning',
  notice: 'info',
  info: 'secondary',
}
const SEVERITY_ORDER = ['fatal', 'error', 'warning', 'notice', 'info']

export function CertificateLintModal({ certId, certName, open, onClose }) {
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

  useEffect(() => {
    if (open) run(profile)
  }, [open, profile, run])

  const summary = result?.summary || {}
  const findings = result?.findings || []

  return (
    <Modal open={open} onClose={onClose}
           title={certName ? t('lint.title', { name: certName }) : t('lint.titleGeneric')}>
      <div className="space-y-3">
        <p className="text-xs text-text-secondary">{t('lint.subtitle')}</p>

        {/* Profile toggle */}
        <div className="flex items-center gap-1">
          {['rfc5280', 'cabf', 'etsi'].map((p) => (
            <Button key={p} type="button" size="sm"
                    variant={profile === p ? 'primary' : 'secondary'}
                    onClick={() => setProfile(p)} disabled={loading}>
              {t(`lint.profile_${p}`)}
            </Button>
          ))}
        </div>

        {loading ? (
          <div className="p-6 text-center text-sm text-text-secondary">{t('common.loading')}</div>
        ) : !available ? (
          <div className="p-6 text-center space-y-1">
            <ShieldWarning size={28} className="mx-auto text-text-tertiary" />
            <p className="text-sm text-text-primary">{t('lint.unavailable')}</p>
            <p className="text-xs text-text-tertiary">{t('lint.unavailableHint')}</p>
          </div>
        ) : (
          <>
            {/* Summary */}
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div className="flex items-center gap-1.5 flex-wrap">
                {SEVERITY_ORDER.map((s) => (
                  summary[s] ? (
                    <Badge key={s} variant={SEVERITY_VARIANT[s]} size="sm">
                      {summary[s]} {t(`lint.severity.${s}`)}
                    </Badge>
                  ) : null
                ))}
                {findings.length === 0 && (
                  <span className="flex items-center gap-1 text-sm text-status-success">
                    <CheckCircle size={16} weight="fill" /> {t('lint.clean')}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 text-2xs text-text-tertiary">
                {result?.detected_type && (
                  <span title={t('lint.detectedType')}>{result.detected_type}</span>
                )}
                {(result?.linters || []).length > 0 && (
                  <span className="font-mono">{(result.linters || []).join(', ')}</span>
                )}
              </div>
            </div>

            {/* Findings */}
            {findings.length > 0 && (
              <div className="max-h-[50vh] overflow-y-auto border border-border rounded-lg divide-y divide-white/5">
                {findings.map((f, i) => (
                  <div key={`${f.code}-${i}`} className="p-2.5 flex items-start gap-2">
                    <Badge variant={SEVERITY_VARIANT[f.severity] || 'secondary'} size="sm">
                      {t(`lint.severity.${f.severity}`)}
                    </Badge>
                    <div className="min-w-0 flex-1">
                      <p className="font-mono text-xs text-text-primary break-all">{f.code}</p>
                      {f.message && <p className="text-xs text-text-secondary mt-0.5">{f.message}</p>}
                      {f.node && <p className="text-3xs text-text-tertiary font-mono mt-0.5 truncate" title={f.node}>{f.node}</p>}
                    </div>
                    <span className="text-3xs text-text-tertiary uppercase">{f.source}</span>
                  </div>
                ))}
              </div>
            )}

            {(profile === 'cabf' || profile === 'etsi') && findings.length > 0 && (
              <p className="flex items-start gap-1.5 text-2xs text-text-tertiary">
                <Warning size={13} className="mt-0.5 shrink-0" />
                {profile === 'etsi' ? t('lint.etsiNote') : t('lint.cabfNote')}
              </p>
            )}
          </>
        )}
      </div>
    </Modal>
  )
}

export default CertificateLintModal
