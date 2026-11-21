/**
 * CrossCertificatesSection — the cross-certificates a CA carries beside its own
 * certificate (#400): list, attach, serve, export, detach, and cross-sign from UCM.
 */
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from '../atelier/Icon'
import { AtelierDialog } from '../atelier/AtelierDialog'
import { IconBtn } from '../atelier/Btn'
import { RecordList, RecordRow } from '../atelier/Detail'
import { casService } from '../../services'
import { useNotification } from '../../contexts'
import { extractData, formatDate, downloadBlob } from '../../lib/utils'
import { certificateFileToPem, commonNameOf, crossStateOf } from '../../lib/crossCertificates'
import { signingCas } from '../../lib/caSelection'
import { sanitizeDownloadName } from '../../lib/filename'

const STATE_TONE = { revoked: 'bad', expired: 'bad', notYetValid: 'warn' }

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

  if (!open) return null
  return (
    <AtelierDialog title={t('crossCerts.attachTitle')} size="narrow" onClose={() => !busy && onClose()} testId="cross-attach-dialog">
      <form onSubmit={submit}>
        <p className="notice"><Icon name="link" /><span>{t('crossCerts.attachHint')}</span></p>
        <div className="form-fields">
          <div className="field full">
            <label htmlFor="cross-attach-pem">{t('cas.uploadCertPaste')}</label>
            <textarea id="cross-attach-pem" className="mono" rows={6} spellCheck={false} placeholder="-----BEGIN CERTIFICATE-----" value={pem}
              onChange={(e) => { setPem(e.target.value); if (e.target.value) setFile(null) }} />
          </div>
          <div className="field full">
            <label htmlFor="cross-attach-file">{t('cas.uploadCertPick')}</label>
            <input id="cross-attach-file" type="file" accept=".pem,.crt,.cer,.der"
              onChange={(e) => { const f = e.target.files?.[0] || null; setFile(f); if (f) setPem('') }} />
          </div>
          <label className="checkbox-line field full">
            <input type="checkbox" checked={served} onChange={(e) => setServed(e.target.checked)} />
            {t('crossCerts.serveNow')}
          </label>
        </div>
        <div className="modal-actions">
          <button type="button" className="btn" onClick={onClose} disabled={busy}>{t('common.cancel')}</button>
          <button type="submit" className="btn primary" data-write="" disabled={busy || (!pem.trim() && !file)}>{t('crossCerts.attach')}</button>
        </div>
      </form>
    </AtelierDialog>
  )
}

function CrossSignModal({ open, onClose, ca, onDone }) {
  const { t } = useTranslation()
  const { showSuccess, showError, showWarning } = useNotification()
  const [issuers, setIssuers] = useState([])
  const [unlistedIssuers, setUnlistedIssuers] = useState(0)
  const [issuerId, setIssuerId] = useState('')
  const [validityDays, setValidityDays] = useState('')
  const [pathLength, setPathLength] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!open) return undefined
    let cancelled = false
    casService.getAll().then((res) => {
      if (cancelled) return
      const others = (extractData(res) || []).filter(c => c.id !== ca.id)
      const usable = signingCas(others).filter(c => c.status === 'Active')
      setIssuers(usable)
      setUnlistedIssuers(others.length - signingCas(others).length)
    }).catch(() => { if (!cancelled) { setIssuers([]); setUnlistedIssuers(0) } })
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

  if (!open) return null
  return (
    <AtelierDialog title={t('crossCerts.signTitle')} size="narrow" onClose={() => !busy && onClose()} testId="cross-sign-dialog">
      <form onSubmit={submit}>
        <p className="notice"><Icon name="stamp" /><span>{t('crossCerts.signHint', { name: ca.name || ca.common_name })}</span></p>
        <div className="form-fields">
          <div className="field full">
            <label htmlFor="cross-sign-issuer">{t('crossCerts.signIssuer')}</label>
            <select id="cross-sign-issuer" value={issuerId} required onChange={(e) => setIssuerId(e.target.value)}
              aria-describedby={unlistedIssuers > 0 ? 'hint-cross-sign-issuer' : undefined}>
              <option value="" disabled>{t('crossCerts.selectIssuer')}</option>
              {issuers.map(c => <option key={c.id} value={c.id}>{c.name || c.common_name}</option>)}
            </select>
            {unlistedIssuers > 0 && <small id="hint-cross-sign-issuer">{t('cas.notListedForSigning', { count: unlistedIssuers })}</small>}
          </div>
          <div className="field">
            <label htmlFor="cross-sign-days">{t('crossCerts.signValidity')}</label>
            <input id="cross-sign-days" type="number" min="1" value={validityDays} onChange={(e) => setValidityDays(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="cross-sign-pathlen">{t('cas.pathLength')}</label>
            <input id="cross-sign-pathlen" type="number" min="0" value={pathLength} onChange={(e) => setPathLength(e.target.value)} />
          </div>
        </div>
        <div className="modal-actions">
          <button type="button" className="btn" onClick={onClose} disabled={busy}>{t('common.cancel')}</button>
          <button type="submit" className="btn primary" data-write="" disabled={busy || !issuerId}>{t('crossCerts.sign')}</button>
        </div>
      </form>
    </AtelierDialog>
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
      downloadBlob(blob, sanitizeDownloadName(ca.name || ca.common_name || 'ca', `-cross-${row.id}.pem`))
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

  // A section of the side panel: the record list of the mockup, one row per cross-certificate
  return (
    <>
      <section className="ca-side-section" data-testid="cross-certificates">
        <h3 className="section-title">{t('crossCerts.title')}</h3>
        <RecordList empty={t('crossCerts.none')}>
          {rows.map((row) => {
            const state = crossStateOf(row)
            return (
              <RecordRow key={row.id}
                title={<span title={row.issuer}>{t('crossCerts.issuedBy', { issuer: commonNameOf(row.issuer) })}</span>}
                meta={`${formatDate(row.valid_from, { time: false })} - ${formatDate(row.valid_to, { time: false })}`}
                extra={(row.served || state) && (
                  <span className="ca-badges">
                    {row.served && <span className="badge good"><Icon name="check" />{t('crossCerts.served')}</span>}
                    {state && <span className={`badge ${STATE_TONE[state]}`}><Icon name={state === 'notYetValid' ? 'clock' : 'warning'} />{t(`crossCerts.state.${state}`)}</span>}
                  </span>
                )}
                action={(
                  <>
                    <IconBtn icon="download" quiet label={t('export.title')} onClick={() => exportRow(row)} />
                    {canWrite && (
                      <>
                        <button type="button" className="btn" data-write="" onClick={() => toggleServed(row)} disabled={!row.served && !!state}>
                          {row.served ? t('crossCerts.stopServing') : t('crossCerts.serve')}
                        </button>
                        <IconBtn icon="close" quiet write label={t('crossCerts.detach')} onClick={() => detach(row)} />
                      </>
                    )}
                  </>
                )}
              />
            )
          })}
        </RecordList>
        {canWrite && (
          <div className="ca-side-tools">
            <button type="button" className="btn" data-write="" onClick={() => setAttachOpen(true)}><Icon name="plus" />{t('crossCerts.attach')}</button>
            <button type="button" className="btn" data-write="" onClick={() => setSignOpen(true)}><Icon name="stamp" />{t('crossCerts.sign')}</button>
          </div>
        )}
      </section>
      {canWrite && <AttachModal open={attachOpen} onClose={() => setAttachOpen(false)} ca={ca} onDone={changed} />}
      {canWrite && <CrossSignModal open={signOpen} onClose={() => setSignOpen(false)} ca={ca} onDone={changed} />}
    </>
  )
}
