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
import { formatDate, downloadBlob } from '../lib/utils'

const STATUS_VARIANTS = { pending: 'warning', approved: 'success', rejected: 'danger', recovered: 'info', cancelled: 'default' }
const FILTERS = ['', 'pending', 'approved', 'recovered', 'rejected']

export default function KeyRecoveryPage() {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
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

  const decide = async (req, action) => {
    const toastKey = action === 'approve' ? 'approved' : 'rejected'
    setBusy(req.id)
    try {
      await keyRecoveryService[action](req.id)
      showSuccess(t(`keyRecovery.${toastKey}`))
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
      const blob = await keyRecoveryService.recover(recoverFor.id, password)
      downloadBlob(blob, `${recoverFor.cert_cn || recoverFor.cert_refid || 'recovered'}.p12`)
      showSuccess(t('keyRecovery.recovered'))
      setRecoverFor(null); setPassword('')
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
        ) : requests.length === 0 ? (
          <EmptyState icon={Vault} title={t('keyRecovery.empty')} description={t('keyRecovery.emptyDesc')} />
        ) : (
          <div className="space-y-2">
            {requests.map((r) => (
              <Card key={r.id} className="p-4">
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-text-primary truncate">{r.cert_cn || r.cert_refid || `#${r.cert_id}`}</span>
                      <Badge variant={STATUS_VARIANTS[r.status] || 'default'} size="sm">{t(`keyRecovery.status.${r.status}`, r.status)}</Badge>
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
                      <Button type="button" size="sm" variant="primary" disabled={busy === r.id} onClick={() => { setRecoverFor(r); setPassword('') }}>
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

      <Modal open={!!recoverFor} onClose={() => { setRecoverFor(null); setPassword('') }} title={t('keyRecovery.recoverTitle')}>
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
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="secondary" onClick={() => { setRecoverFor(null); setPassword('') }}>{t('common.cancel')}</Button>
            <Button type="button" variant="primary" disabled={busy === recoverFor?.id || password.length < 8} onClick={doRecover}>
              <DownloadSimple size={16} /> {t('keyRecovery.download')}
            </Button>
          </div>
        </div>
      </Modal>
    </ResponsiveLayout>
  )
}
