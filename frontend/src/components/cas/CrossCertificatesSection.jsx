/**
 * CrossCertificatesSection — the cross-certificates a CA carries beside its own
 * certificate (#400): list, attach, serve, export, detach, and cross-sign from UCM.
 */
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus, Trash, DownloadSimple, Signature, UploadSimple } from '@phosphor-icons/react'
import { Badge } from '../Badge'
import { Button } from '../Button'
import { CompactSection } from '../DetailCard'
import { Modal } from '../Modal'
import { casService } from '../../services'
import { useNotification } from '../../contexts'
import { extractData, formatDate, downloadBlob } from '../../lib/utils'
import { certificateFileToPem, commonNameOf, crossStateOf } from '../../lib/crossCertificates'

const STATE_VARIANT = { revoked: 'danger', expired: 'danger', notYetValid: 'warning' }
const FIELD = 'w-full px-3 py-2 bg-bg-tertiary border border-border rounded-md text-sm text-text-primary focus:outline-none focus:border-accent-primary'

function AttachModal({ open, onClose, ca, onDone }) {
  const { t } = useTranslation()
  const { showSuccess, showError, showWarning } = useNotification()
  const [pem, setPem] = useState('')
  const [file, setFile] = useState(null)
  const [served, setServed] = useState(false)
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e?.preventDefault?.()
    setBusy(true)
    try {
      const certificate = file ? await certificateFileToPem(file) : pem.trim()
      const res = await casService.attachCrossCertificate(ca.id, certificate, { served })
      for (const w of extractData(res)?.warnings || []) showWarning(w)
      showSuccess(t('crossCerts.attached'))
      setPem(''); setFile(null); setServed(false)
      onDone()
      onClose()
    } catch (err) {
      showError(err?.message || t('crossCerts.attachFailed'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal open={open} onOpenChange={(v) => !v && !busy && onClose()} title={t('crossCerts.attachTitle')} size="md">
      <form onSubmit={submit} className="p-4 space-y-3">
        <p className="text-xs text-text-secondary">{t('crossCerts.attachHint')}</p>
        <textarea className={`${FIELD} h-32 font-mono text-xs resize-y`} spellCheck={false}
                  placeholder="-----BEGIN CERTIFICATE-----" value={pem}
                  onChange={(e) => { setPem(e.target.value); if (e.target.value) setFile(null) }} />
        <label className="flex items-center gap-2 px-3 py-2 bg-bg-tertiary border border-border rounded-md cursor-pointer">
          <UploadSimple size={16} className="text-text-tertiary" />
          <span className="text-sm text-text-primary truncate">{file ? file.name : t('cas.uploadCertPick')}</span>
          <input type="file" className="hidden" accept=".pem,.crt,.cer,.der"
                 onChange={(e) => { const f = e.target.files?.[0] || null; setFile(f); if (f) setPem('') }} />
        </label>
        <label className="flex items-center gap-2 text-sm text-text-primary">
          <input type="checkbox" className="w-4 h-4 accent-accent-primary" checked={served}
                 onChange={(e) => setServed(e.target.checked)} />
          {t('crossCerts.serveNow')}
        </label>
        <div className="flex justify-end gap-2 pt-3 border-t border-border">
          <Button type="button" variant="secondary" onClick={onClose} disabled={busy}>{t('common.cancel')}</Button>
          <Button type="submit" variant="primary" loading={busy} disabled={!pem.trim() && !file}>
            {t('crossCerts.attach')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

function CrossSignModal({ open, onClose, ca, onDone }) {
  const { t } = useTranslation()
  const { showSuccess, showError, showWarning } = useNotification()
  const [issuers, setIssuers] = useState([])
  const [issuerId, setIssuerId] = useState('')
  const [validityDays, setValidityDays] = useState('')
  const [pathLength, setPathLength] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!open) return undefined
    let cancelled = false
    casService.getAll().then((res) => {
      if (cancelled) return
      const all = extractData(res) || []
      setIssuers(all.filter(c => c.id !== ca.id && c.crt !== null && !c.pending && !c.offline && !c.revoked
        && c.status === 'Active' && (c.has_private_key || c.uses_hsm)))
    }).catch(() => { if (!cancelled) setIssuers([]) })
    return () => { cancelled = true }
  }, [open, ca.id])

  const submit = async (e) => {
    e?.preventDefault?.()
    setBusy(true)
    try {
      const res = await casService.crossSign(Number(issuerId), {
        subjectCaId: ca.id,
        validityDays: validityDays ? Number(validityDays) : undefined,
        pathLength: pathLength === '' ? undefined : Number(pathLength),
      })
      for (const w of extractData(res)?.warnings || []) showWarning(w)
      showSuccess(t('crossCerts.signed'))
      onDone()
      onClose()
    } catch (err) {
      showError(err?.message || t('crossCerts.signFailed'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal open={open} onOpenChange={(v) => !v && !busy && onClose()} title={t('crossCerts.signTitle')} size="md">
      <form onSubmit={submit} className="p-4 space-y-3">
        <p className="text-xs text-text-secondary">{t('crossCerts.signHint', { name: ca.name || ca.common_name })}</p>
        <div className="space-y-1">
          <label htmlFor="cross-sign-issuer" className="block text-xs font-medium text-text-secondary">
            {t('crossCerts.signIssuer')}
          </label>
          <select id="cross-sign-issuer" className={FIELD} value={issuerId} required
                  onChange={(e) => setIssuerId(e.target.value)}>
            <option value="" disabled>{t('crossCerts.selectIssuer')}</option>
            {issuers.map(c => <option key={c.id} value={c.id}>{c.name || c.common_name}</option>)}
          </select>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <label htmlFor="cross-sign-days" className="block text-xs font-medium text-text-secondary">
              {t('crossCerts.signValidity')}
            </label>
            <input id="cross-sign-days" type="number" min="1" className={FIELD} value={validityDays}
                   onChange={(e) => setValidityDays(e.target.value)} />
          </div>
          <div className="space-y-1">
            <label htmlFor="cross-sign-pathlen" className="block text-xs font-medium text-text-secondary">
              {t('cas.pathLength')}
            </label>
            <input id="cross-sign-pathlen" type="number" min="0" className={FIELD} value={pathLength}
                   onChange={(e) => setPathLength(e.target.value)} />
          </div>
        </div>
        <div className="flex justify-end gap-2 pt-3 border-t border-border">
          <Button type="button" variant="secondary" onClick={onClose} disabled={busy}>{t('common.cancel')}</Button>
          <Button type="submit" variant="primary" loading={busy} disabled={!issuerId}>{t('crossCerts.sign')}</Button>
        </div>
      </form>
    </Modal>
  )
}

export function CrossCertificatesSection({ ca, canWrite }) {
  const { t } = useTranslation()
  const { showSuccess, showError, showConfirm } = useNotification()
  const [rows, setRows] = useState(null)
  const [attachOpen, setAttachOpen] = useState(false)
  const [signOpen, setSignOpen] = useState(false)

  const load = useCallback(async () => {
    try {
      setRows(extractData(await casService.getCrossCertificates(ca.id)) || [])
    } catch {
      setRows([])
    }
  }, [ca.id])

  useEffect(() => {
    setRows(null)
    if (ca?.id && !ca.pending) load()
  }, [ca?.id, ca?.pending, load])

  const changed = () => {
    load()
    window.dispatchEvent(new CustomEvent('ucm:data-changed', { detail: { type: 'ca' } }))
  }

  if (ca.pending || rows === null) return null
  if (rows.length === 0 && !canWrite) return null

  const toggleServed = async (row) => {
    try {
      await casService.setCrossCertificateServed(ca.id, row.id, !row.served)
      showSuccess(t(row.served ? 'crossCerts.unserved' : 'crossCerts.servedNow'))
      changed()
    } catch (err) {
      showError(err?.message || t('crossCerts.updateFailed'))
    }
  }

  const exportRow = async (row) => {
    try {
      const blob = await casService.exportCrossCertificate(ca.id, row.id, 'pem')
      downloadBlob(blob, `${(ca.name || ca.common_name || 'ca').replace(/[^a-zA-Z0-9._-]+/g, '_')}-cross-${row.id}.pem`)
    } catch (err) {
      showError(err?.message || t('cas.exportFailed'))
    }
  }

  const detach = async (row) => {
    const confirmed = await showConfirm(t('crossCerts.detachConfirm', { issuer: commonNameOf(row.issuer) }), {
      title: t('crossCerts.detach'), variant: 'danger', confirmText: t('crossCerts.detach'),
    })
    if (!confirmed) return
    try {
      await casService.detachCrossCertificate(ca.id, row.id)
      showSuccess(t('crossCerts.detached'))
      changed()
    } catch (err) {
      showError(err?.message || t('crossCerts.updateFailed'))
    }
  }

  return (
    <>
      <CompactSection title={t('crossCerts.title')}>
        <div className="space-y-2" data-testid="cross-certificates">
          {rows.length === 0 && <p className="text-2xs text-text-secondary">{t('crossCerts.none')}</p>}
          {rows.map(row => {
            const state = crossStateOf(row)
            return (
              <div key={row.id} className="p-2.5 bg-tertiary-50 border border-border rounded-lg space-y-1">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0 flex-wrap">
                    <span className="text-xs font-medium text-text-primary truncate" title={row.issuer}>
                      {t('crossCerts.issuedBy', { issuer: commonNameOf(row.issuer) })}
                    </span>
                    {row.served && <Badge variant="success" size="sm">{t('crossCerts.served')}</Badge>}
                    {state && <Badge variant={STATE_VARIANT[state]} size="sm">{t(`crossCerts.state.${state}`)}</Badge>}
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <Button type="button" size="xs" variant="secondary" onClick={() => exportRow(row)}
                            title={t('export.title')} aria-label={t('export.title')}>
                      <DownloadSimple size={12} />
                    </Button>
                    {canWrite && (
                      <>
                        <Button type="button" size="xs" variant="secondary" onClick={() => toggleServed(row)}
                                disabled={!row.served && !!state}>
                          {row.served ? t('crossCerts.stopServing') : t('crossCerts.serve')}
                        </Button>
                        <Button type="button" size="xs" variant="danger" onClick={() => detach(row)}
                                title={t('crossCerts.detach')} aria-label={t('crossCerts.detach')}>
                          <Trash size={12} />
                        </Button>
                      </>
                    )}
                  </div>
                </div>
                <p className="text-2xs text-text-tertiary">
                  {formatDate(row.valid_from)} - {formatDate(row.valid_to)}
                </p>
              </div>
            )
          })}
          {canWrite && (
            <div className="flex flex-wrap gap-1.5">
              <Button type="button" size="xs" variant="secondary" onClick={() => setAttachOpen(true)}>
                <Plus size={12} /> {t('crossCerts.attach')}
              </Button>
              <Button type="button" size="xs" variant="secondary" onClick={() => setSignOpen(true)}>
                <Signature size={12} /> {t('crossCerts.sign')}
              </Button>
            </div>
          )}
        </div>
      </CompactSection>
      {canWrite && <AttachModal open={attachOpen} onClose={() => setAttachOpen(false)} ca={ca} onDone={changed} />}
      {canWrite && <CrossSignModal open={signOpen} onClose={() => setSignOpen(false)} ca={ca} onDone={changed} />}
    </>
  )
}
