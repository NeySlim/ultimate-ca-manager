import { useState, useEffect, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Pulse, CheckCircle, XCircle, Warning, ArrowsClockwise } from '@phosphor-icons/react'
import { Modal } from './Modal'
import { Button } from './Button'
import { Badge } from './Badge'
import { useNotification } from '../contexts'
import { mscaService } from '../services'
import { formatDate } from '../lib/utils'

export function MscaCaControlModal({ connection, open, onClose }) {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  const [loading, setLoading] = useState(false)
  const [health, setHealth] = useState(null)
  const [pending, setPending] = useState([])
  const [busyId, setBusyId] = useState(null)
  const loadingRef = useRef(false)

  const connId = connection?.id

  const load = useCallback(async () => {
    if (loadingRef.current || !connId) return
    loadingRef.current = true
    setLoading(true)
    try {
      const [h, p] = await Promise.all([
        mscaService.caHealth(connId).catch(() => null),
        mscaService.caPending(connId).catch(() => ({ data: [] })),
      ])
      setHealth(h?.data || null)
      setPending(p?.data || [])
    } catch (e) {
      showError(e.message || t('msca.caControlLoadFailed'))
    } finally {
      loadingRef.current = false
      setLoading(false)
    }
  }, [connId, t, showError])

  useEffect(() => {
    if (open) load()
  }, [open, load])

  const handleApprove = async (rid) => {
    setBusyId(rid)
    try {
      const res = await mscaService.approveRequest(connId, rid)
      showSuccess(res.data?.imported_cert_id
        ? t('msca.approveImported')
        : t('msca.approveSuccess'))
      load()
    } catch (e) {
      showError(e.message || t('msca.approveFailed'))
    } finally {
      setBusyId(null)
    }
  }

  const handleDeny = async (rid) => {
    setBusyId(rid)
    try {
      await mscaService.denyRequest(connId, rid)
      showSuccess(t('msca.denySuccess'))
      load()
    } catch (e) {
      showError(e.message || t('msca.denyFailed'))
    } finally {
      setBusyId(null)
    }
  }

  const svcOk = health?.certsvc_status === 'Running'
  const caDays = health?.ca_cert?.days_until_expiry
  const crlExpired = health?.crl?.expired

  return (
    <Modal open={open} onClose={onClose}
           title={t('msca.caControlTitle', { name: connection?.name || '' })}>
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <p className="text-xs text-text-secondary">{t('msca.caControlSubtitle')}</p>
          <Button type="button" size="sm" variant="secondary" onClick={load} disabled={loading}>
            <ArrowsClockwise size={14} className={loading ? 'animate-spin' : ''} />
            {t('common.refresh')}
          </Button>
        </div>

        {/* Health */}
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <div className="p-2.5 rounded-lg bg-tertiary-50 border border-border">
            <p className="text-2xs text-text-tertiary uppercase">{t('msca.healthService')}</p>
            <p className={`text-sm font-medium ${svcOk ? 'text-status-success' : 'text-status-danger'}`}>
              {health?.certsvc_status || '—'}
            </p>
          </div>
          <div className="p-2.5 rounded-lg bg-tertiary-50 border border-border">
            <p className="text-2xs text-text-tertiary uppercase">{t('msca.healthCaExpiry')}</p>
            <p className={`text-sm font-medium ${caDays != null && caDays < 90 ? 'text-status-warning' : 'text-text-primary'}`}>
              {caDays != null ? t('msca.daysCount', { count: caDays }) : '—'}
            </p>
          </div>
          <div className="p-2.5 rounded-lg bg-tertiary-50 border border-border">
            <p className="text-2xs text-text-tertiary uppercase">{t('msca.healthCrl')}</p>
            <p className={`text-sm font-medium ${crlExpired ? 'text-status-danger' : 'text-text-primary'}`}>
              {health?.crl?.next_update ? formatDate(health.crl.next_update) : '—'}
            </p>
          </div>
          <div className="p-2.5 rounded-lg bg-tertiary-50 border border-border">
            <p className="text-2xs text-text-tertiary uppercase">{t('msca.healthPending')}</p>
            <p className="text-sm font-medium text-text-primary">{health?.pending_count ?? '—'}</p>
          </div>
        </div>

        {(health?.warnings || []).length > 0 && (
          <div className="space-y-1">
            {health.warnings.map((w, i) => (
              <p key={i} className="flex items-start gap-1.5 text-2xs text-status-warning">
                <Warning size={13} className="mt-0.5 shrink-0" />{w}
              </p>
            ))}
          </div>
        )}

        {/* Pending requests */}
        <div>
          <p className="text-sm font-medium text-text-primary mb-2">
            {t('msca.pendingRequests')} {pending.length > 0 && <Badge variant="warning" size="sm">{pending.length}</Badge>}
          </p>
          {loading ? (
            <p className="p-4 text-center text-sm text-text-secondary">{t('common.loading')}</p>
          ) : pending.length === 0 ? (
            <p className="p-4 text-center text-sm text-text-tertiary flex items-center justify-center gap-1.5">
              <CheckCircle size={16} weight="fill" className="text-status-success" />
              {t('msca.noPending')}
            </p>
          ) : (
            <div className="border border-border rounded-lg divide-y divide-white/5 max-h-[40vh] overflow-y-auto">
              {pending.map((r) => (
                <div key={r.request_id} className="p-2.5 flex items-center gap-2">
                  <div className="min-w-0 flex-1">
                    <p className="text-xs text-text-primary truncate">
                      <span className="font-mono text-text-tertiary">#{r.request_id}</span> {r.subject_cn || '—'}
                    </p>
                    <p className="text-2xs text-text-tertiary truncate">
                      {r.requester_name} · {r.template} · {r.submitted_when}
                    </p>
                  </div>
                  <Button type="button" size="sm" variant="primary"
                          onClick={() => handleApprove(r.request_id)} disabled={busyId === r.request_id}>
                    <CheckCircle size={13} /> {t('msca.approve')}
                  </Button>
                  <Button type="button" size="sm" variant="danger"
                          onClick={() => handleDeny(r.request_id)} disabled={busyId === r.request_id}>
                    <XCircle size={13} /> {t('msca.deny')}
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </Modal>
  )
}

export default MscaCaControlModal
