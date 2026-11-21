/**
 * KeyRecoveryPage — dual-control private-key recovery (escrow).
 * Review recovery requests, approve/reject (admin), and download the recovered
 * key as PKCS#12 after approval.
 */
import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Vault, CheckCircle, XCircle, Clock, DownloadSimple, Warning } from '@phosphor-icons/react'
import {
  ResponsiveLayout, Card, Button, Badge, Input, Modal, LoadingSpinner, EmptyState,
} from '../components'
import { keyRecoveryService } from '../services'
import { useNotification } from '../contexts'
import { usePermission } from '../hooks'
import { useLinkedId } from '../hooks/useLinkedId'
import { stateLabel } from '../lib/stateLabel'
import { formatDate, downloadBlob } from '../lib/utils'

const STATUS_VARIANTS = { pending: 'warning', approved: 'success', rejected: 'danger', recovered: 'info', cancelled: 'default' }
const FILTERS = ['', 'pending', 'approved', 'recovered', 'rejected']

export default function KeyRecoveryPage() {
  const { t } = useTranslation()
  const { showSuccess, showError, showInfo } = useNotification()
  const { hasPermission } = usePermission()
  const isAdmin = hasPermission('admin:key_recovery')
  const canRecover = hasPermission('write:key_recovery')

  const [requests, setRequests] = useState([])
  const [dualControl, setDualControl] = useState(true)
  const [loading, setLoading] = useState(false)
  const [statusFilter, setStatusFilter] = useState('')
  const [busy, setBusy] = useState(null)
  const [recoverFor, setRecoverFor] = useState(null)
  const [password, setPassword] = useState('')
  const [legacy, setLegacy] = useState(false)  // PKCS#12 3DES/SHA-1 profile (#331)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await keyRecoveryService.list(statusFilter || undefined)
      const data = res.data || res
      setRequests(data.requests || [])
      setDualControl(data.dual_control !== false)
    } catch (e) {
      showError(e.message || t('keyRecovery.loadFailed'))
    } finally {
      setLoading(false)
    }
  }, [statusFilter, showError, t])

  useEffect(() => { load() }, [load])

  // /key-recovery?request=N shows that request, even past the 500 the list holds
  const linkedId = useLinkedId('request')
  const [linked, setLinked] = useState(null)
  useEffect(() => {
    if (!linkedId) return
    let cancelled = false
    keyRecoveryService.get(linkedId)
      .then((res) => {
        if (cancelled) return
        const row = res.data || res
        setLinked(row)
        if (row.status !== 'pending') {
          showInfo(t('overview.link.handled', { id: row.id, status: stateLabel(t, row.status) }))
        }
      })
      .catch((e) => {
        if (cancelled) return
        if (e?.status === 404) showInfo(t('overview.link.gone', { id: linkedId }))
        else showError(e.message || t('keyRecovery.loadFailed'))
      })
    return () => { cancelled = true }
  }, [linkedId, showError, showInfo, t])
  // The linked request comes first, in its listed copy when there is one, and only while the filter keeps its state
  const current = linked && (requests.find((r) => r.id === linked.id) || linked)
  const rest = current ? requests.filter((r) => r.id !== current.id) : requests
  const shown = current && (!statusFilter || current.status === statusFilter) ? [current, ...rest] : rest

  // A decision on the linked request re-reads it: the filtered list may no longer hold it
  const refreshLinked = async (id) => {
    if (linked?.id !== id) return
    try {
      const res = await keyRecoveryService.get(id)
      setLinked(res.data || res)
    } catch {
      setLinked(null)
    }
  }

  const decide = async (req, action) => {
    const toastKey = action === 'approve' ? 'approved' : 'rejected'
    setBusy(req.id)
    try {
      await keyRecoveryService[action](req.id)
      showSuccess(t(`keyRecovery.${toastKey}`))
      await refreshLinked(req.id)
      await load()
    } catch (e) {
      showError(e.message || t('keyRecovery.actionFailed'))
    } finally {
      setBusy(null)
    }
  }

  const doRecover = async () => {
    if (password.length < 8) { showError(t('keyRecovery.passwordTooShort')); return }
    setBusy(recoverFor.id)
    try {
      const blob = await keyRecoveryService.recover(recoverFor.id, password, legacy)
      downloadBlob(blob, `${recoverFor.cert_cn || recoverFor.cert_refid || 'recovered'}.p12`)
      showSuccess(t('keyRecovery.recovered'))
      setRecoverFor(null); setPassword(''); setLegacy(false)
      await refreshLinked(recoverFor.id)
      await load()
    } catch (e) {
      showError(e.message || t('keyRecovery.actionFailed'))
    } finally {
      setBusy(null)
    }
  }

  return (
    <ResponsiveLayout title={t('keyRecovery.title')} subtitle={t('keyRecovery.subtitle')} icon={Vault} helpPageKey="keyRecovery">
      <div className="p-3 sm:p-4 space-y-3">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex gap-1">
            {FILTERS.map((s) => (
              <Button key={s || 'all'} type="button" size="sm"
                      variant={statusFilter === s ? 'primary' : 'secondary'}
                      onClick={() => setStatusFilter(s)}>
                {s ? t(`keyRecovery.status.${s}`) : t('common.all')}
              </Button>
            ))}
          </div>
          {dualControl && (
            <Badge variant="info" size="sm">{t('keyRecovery.dualControlOn')}</Badge>
          )}
        </div>

        {loading ? (
          <div className="flex justify-center py-12"><LoadingSpinner /></div>
        ) : shown.length === 0 ? (
          <EmptyState icon={Vault} title={t('keyRecovery.empty')} description={t('keyRecovery.emptyDesc')} />
        ) : (
          <div className="space-y-2">
            {shown.map((r) => (
              <Card key={r.id} className={`p-4 ${linked?.id === r.id ? 'ring-2 ring-accent-primary' : ''}`}
                    aria-current={linked?.id === r.id ? 'true' : undefined}>
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-text-primary truncate">{r.cert_cn || r.cert_refid || `#${r.cert_id}`}</span>
                      <Badge variant={STATUS_VARIANTS[r.status] || 'default'} size="sm">{t(`keyRecovery.status.${r.status}`, stateLabel(t, r.status))}</Badge>
                    </div>
                    <p className="text-xs text-text-secondary mt-1">{t('keyRecovery.reason')}: {r.reason}</p>
                    <p className="text-2xs text-text-tertiary mt-1">
                      {t('keyRecovery.requestedBy', { user: r.requested_by })} · {formatDate(r.requested_at)}
                      {r.decided_by && <> · {t('keyRecovery.decidedBy', { user: r.decided_by })}</>}
                      {r.recovered_by && <> · {t('keyRecovery.recoveredBy', { user: r.recovered_by })}</>}
                    </p>
                    {r.decision_note && <p className="text-2xs text-text-tertiary mt-0.5 italic">“{r.decision_note}”</p>}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {r.status === 'pending' && isAdmin && (
                      <>
                        <Button type="button" size="sm" variant="success-soft" disabled={busy === r.id} onClick={() => decide(r, 'approve')}>
                          <CheckCircle size={14} /> {t('keyRecovery.approve')}
                        </Button>
                        <Button type="button" size="sm" variant="danger-soft" disabled={busy === r.id} onClick={() => decide(r, 'reject')}>
                          <XCircle size={14} /> {t('keyRecovery.reject')}
                        </Button>
                      </>
                    )}
                    {r.status === 'approved' && canRecover && (
                      <Button type="button" size="sm" variant="primary" disabled={busy === r.id} onClick={() => { setRecoverFor(r); setPassword(''); setLegacy(false) }}>
                        <DownloadSimple size={14} /> {t('keyRecovery.recover')}
                      </Button>
                    )}
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>

      <Modal open={!!recoverFor} onClose={() => { setRecoverFor(null); setPassword(''); setLegacy(false) }} title={t('keyRecovery.recoverTitle')}>
        <div className="p-4 space-y-3">
          <p className="flex items-start gap-1.5 text-xs text-text-secondary">
            <Warning size={14} className="mt-0.5 shrink-0 text-status-warning" />
            {t('keyRecovery.recoverWarning')}
          </p>
          <Input
            type="password"
            label={t('keyRecovery.p12Password')}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={t('keyRecovery.p12PasswordHint')}
            autoFocus
          />
          <label className="flex items-center gap-2.5 px-1 py-1 cursor-pointer">
            <input
              type="checkbox"
              checked={legacy}
              onChange={(e) => setLegacy(e.target.checked)}
              className="w-4 h-4 rounded accent-accent-primary"
            />
            <div>
              <div className="text-sm text-text-primary">{t('export.legacyPkcs12')}</div>
              <div className="text-xs text-text-tertiary">{t('export.legacyPkcs12Desc')}</div>
            </div>
          </label>
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="secondary" onClick={() => { setRecoverFor(null); setPassword(''); setLegacy(false) }}>{t('common.cancel')}</Button>
            <Button type="button" variant="primary" disabled={busy === recoverFor?.id || password.length < 8} onClick={doRecover}>
              <DownloadSimple size={16} /> {t('keyRecovery.download')}
            </Button>
          </div>
        </div>
      </Modal>
    </ResponsiveLayout>
  )
}
