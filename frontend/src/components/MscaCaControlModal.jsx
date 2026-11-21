import { useState, useEffect, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Btn, Props, RecordList, RecordRow, Section } from './atelier'
import { Modal, Notice } from './atelier/Form'
import { useNotification } from '../contexts'
import { mscaService } from '../services'
import { formatDate } from '../lib/utils'

export function MscaCaControlModal({ connection, open, onClose }) {
  const { t } = useTranslation()
  const { showSuccess, showError, showConfirm } = useNotification()
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

  // Read when the dialog opens on a connection, not again each time `load` is rebuilt
  const loadRef = useRef(load)
  loadRef.current = load
  useEffect(() => {
    if (open) loadRef.current()
  }, [open, connId])

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
    // Applied on the remote CA, audited there, and not undoable from here.
    const confirmed = await showConfirm(t('msca.denyConfirm', { id: rid }), {
      title: t('msca.deny'),
      confirmText: t('msca.deny'),
      variant: 'danger',
    })
    if (!confirmed) return
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

  // The mockup's dialog: the health as props, the warnings as notices, the pending requests as records
  return (
    <Modal open={open} onClose={onClose} title={t('msca.caControlTitle', { name: connection?.name || '' })} subtitle={t('msca.caControlSubtitle')}>
      <div className="settings-stack">
      <div className="settings-actions">
        <Btn icon="refresh" onClick={load} disabled={loading || undefined}>{t('common.refresh')}</Btn>
      </div>
      <Section title={t('msca.caControl')}>
        <Props items={[
          [t('msca.healthService'), <span key="s" className={health?.certsvc_status ? (svcOk ? 'good' : 'bad') : undefined}>{health?.certsvc_status || '—'}</span>],
          [t('msca.healthCaExpiry'), <span key="e" className={caDays != null && caDays < 90 ? 'warn' : undefined}>{caDays != null ? t('msca.daysCount', { count: caDays }) : '—'}</span>],
          [t('msca.healthCrl'), <span key="c" className={crlExpired ? 'bad' : undefined}>{health?.crl?.next_update ? formatDate(health.crl.next_update) : '—'}</span>],
          [t('msca.healthPending'), health?.pending_count ?? '—'],
        ]} />
      </Section>
      {(health?.warnings || []).map((w, i) => <Notice key={i} tone="warn">{w}</Notice>)}
      <Section title={<>{t('msca.pendingRequests')}{pending.length > 0 && <span className="counter">{pending.length}</span>}</>}>
        {loading ? (
          <p className="muted small">{t('common.loading')}</p>
        ) : (
          <RecordList empty={t('msca.noPending')}>
            {pending.map((r) => (
              <RecordRow key={r.request_id}
                title={<><span className="mono">#{r.request_id}</span> {r.subject_cn || '—'}</>}
                meta={`${r.requester_name} · ${r.template} · ${r.submitted_when}`}
                action={<>
                  <Btn tone="primary" icon="check" onClick={() => handleApprove(r.request_id)} disabled={busyId === r.request_id || undefined}>{t('msca.approve')}</Btn>
                  <Btn tone="danger" icon="close" onClick={() => handleDeny(r.request_id)} disabled={busyId === r.request_id || undefined}>{t('msca.deny')}</Btn>
                </>} />
            ))}
          </RecordList>
        )}
      </Section>
      </div>
    </Modal>
  )
}

export default MscaCaControlModal
