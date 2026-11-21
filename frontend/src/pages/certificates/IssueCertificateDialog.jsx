/**
 * The dialog around IssueCertificateForm, for an issuance (Certificates page) or a renewal
 * (inspector): it sends the reviewed request, then says what came of it in a result screen
 * (issued, renewed, or held for approval). The focus goes back to the opener when it closes.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { useInRouterContext, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { AtelierDialog } from '../../components/atelier/AtelierDialog'
import { Icon } from '../../components/atelier/Icon'
import { certificatesService, csrsService, casService } from '../../services'
import { useNotification } from '../../contexts'
import { usePermission } from '../../hooks'
import { issueWithSubjectOverride } from '../../lib/uniqueSubject'
import { noticesOf } from '../../lib/notices'
import { IssueCertificateForm } from './IssueCertificateForm'

const P = 'certificates.issueForm.'

function ViewApproval({ id, onDone, t }) {
  const navigate = useNavigate()
  return (
    <button type="button" className="btn primary" data-write="false" onClick={() => { onDone(); navigate(`/approvals?id=${id}`) }}>
      {t(`${P}resultViewApproval`)}
    </button>
  )
}

/** The screen after the request went out: what happened, and where to look at it. */
function Result({ result, onClose, onOpen, canSeeApprovals, inRouter, t }) {
  const held = result.kind === 'approval'
  const waiting = result.kind === 'pending'
  const strong = (key, params) => {
    const marker = '\u0000'
    const [a, b] = String(t(key, { ...params, name: marker })).split(marker)
    return b === undefined ? a : <>{a}<strong>{result.name}</strong>{b}</>
  }
  return (
    <div data-testid="issue-result">
      <div className={held || waiting ? 'result-icon warn' : 'result-icon'}>
        <Icon name={held ? 'warning' : waiting ? 'clock' : 'check'} />
      </div>
      <h3 className="result-title">{t(`${P}result.${result.kind}.title`)}</h3>
      <p className="result-copy">
        {strong(`${P}result.${result.kind}.copy`, { policy: result.policy ?? '' })}
        {result.related && <> {t(result.related.key, result.related.params)}</>}
      </p>
      {result.notices?.map((notice) => (
        <div className="notice warn" style={{ marginTop: 20 }} key={notice}><Icon name="warning" /><span>{notice}</span></div>
      ))}
      <div className="modal-actions">
        <button type="button" className="btn" data-action="close-modal" onClick={onClose}>{t('common.close')}</button>
        {held && result.approvalId != null && canSeeApprovals && inRouter && (
          <ViewApproval id={result.approvalId} onDone={onClose} t={t} />
        )}
        {!held && !waiting && result.certificate && (
          <button type="button" className="btn primary" data-write="false" data-result-open={result.certificate.id} onClick={() => onOpen(result.certificate)}>{t(`${P}resultViewCertificate`)}</button>
        )}
      </div>
    </div>
  )
}

/**
 * @param {object} p
 * @param {boolean} p.open
 * @param {(open: boolean) => void} p.onOpenChange
 * @param {'issue'|'renew'} [p.mode]
 * @param {object} [p.certificate]  the certificate a renewal starts from
 * @param {object[]} [p.cas]  the CAs to choose from; loaded here when absent
 * @param {object} [p.initialData]  a prefill (re-key from a CSR, the authority an issuance starts from)
 * @param {(issued: object|null) => void} [p.onIssued]  once a certificate was issued or renewed
 * @param {(issued: object) => void} [p.onOpen]  "View the certificate" of the result screen
 * @param {() => void} [p.onMutate]  just before a mutating request
 */
export function IssueCertificateDialog({
  open, onOpenChange, mode = 'issue', certificate = null, cas, initialData, onIssued, onOpen, onMutate,
}) {
  const { t } = useTranslation()
  const { showConfirm } = useNotification()
  const { hasPermission } = usePermission()
  const inRouter = useInRouterContext()
  const [step, setStep] = useState(1)
  const [result, setResult] = useState(null)
  // While the request is out the dialog stays: its answer always reaches the result screen
  const sendingRef = useRef(false)
  const [loadedCas, setLoadedCas] = useState([])
  // One upload per CSR text: a retry after a refused signature signs the request already uploaded
  const [uploaded, setUploaded] = useState({ pem: null, id: null })
  const renew = mode === 'renew'
  // The dialog's own close button (the mockup's « Fermer la fenêtre »)
  const closeButton = () => document.querySelector('[data-testid="issue-dialog"] .modal-head [data-action="close-modal"]')

  useEffect(() => {
    if (!open || cas) return undefined
    let cancelled = false
    // A renewal reads them only to name the issuer's level: a failure leaves its name alone
    Promise.resolve().then(() => casService.getAll())
      .then((res) => { if (!cancelled) setLoadedCas(res?.data || []) }).catch(() => {})
    return () => { cancelled = true }
  }, [open, cas])
  useEffect(() => { if (!open) { setStep(1); setResult(null) } }, [open])

  const close = () => onOpenChange(false)
  // Escape and the close button both go through here: neither closes while the request is out
  const changeOpen = (next) => { if (next || !sendingRef.current) onOpenChange(next) }
  const busy = (on) => { sendingRef.current = on }

  // The form names its operation; without it, the dialog's mode decides
  const submit = useCallback(async (body, { kind = renew ? 'renew' : 'issue', csr } = {}) => {
    onMutate?.()
    const name = certificate?.cn || certificate?.common_name || body.cn || ''
    if (kind === 'renew') {
      const res = await certificatesService.renew(certificate.id, body)
      if (res?.data?.approval_required) {
        return { result: { kind: 'approval', name, policy: res.data.policy_name ?? '', approvalId: res.data.approval_id } }
      }
      onIssued?.(res?.data || null)
      if (res?.meta?.msca_status === 'pending') return { result: { kind: 'pending', name } }
      const related = res?.data?.related_renewed
      return {
        result: {
          kind: 'renewed', name, certificate: res?.data?.id ? res.data : certificate, notices: noticesOf(res),
          related: related?.length ? { key: 'certificates.hybrid.renewedWithRelated', params: { id: related.join(', #') } } : null,
        },
      }
    }
    let response
    if (kind === 'csr') {
      let csrId = uploaded.pem === csr ? uploaded.id : null
      if (!csrId) {
        const res = await csrsService.upload(csr)
        csrId = res?.data?.id
        setUploaded({ pem: csr, id: csrId })
      }
      const { ca_id, validity_days, cert_type, extra_ekus = [], ...rest } = body
      response = await issueWithSubjectOverride(
        (options) => csrsService.sign(csrId, ca_id, validity_days, cert_type, extra_ekus, {}, { ...rest, ...options }),
        showConfirm, t)
    } else {
      response = await issueWithSubjectOverride(
        (options) => certificatesService.create({ ...body, ...options }), showConfirm, t)
    }
    if (response === null) return { cancelled: true }  // the operator kept the refusal of a taken subject
    if (response?.data?.approval_required) {
      return { result: { kind: 'approval', name, policy: response.data.policy_name ?? '', approvalId: response.data.approval_id } }
    }
    // A hybrid pair answers { certificate: classical, related: ML-DSA }
    const pair = response?.data?.certificate ? response.data : null
    const issued = pair ? pair.certificate : response?.data
    onIssued?.(issued?.id ? issued : null)
    return {
      result: {
        kind: 'issued', name: issued?.cn || issued?.common_name || name, certificate: issued?.id ? issued : null,
        notices: noticesOf(response),
        related: pair ? { key: 'certificates.hybrid.pairIssued', params: { classical: pair.certificate.id, pq: pair.related?.id } } : null,
      },
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [renew, certificate, uploaded, onIssued, onMutate, t])

  const sent = useCallback((outcome) => {
    if (!outcome?.result) return
    setResult(outcome.result)
    // The result screen replaces the form: its close button takes the focus, as in the Atelier
    setTimeout(() => closeButton()?.focus())
  }, [])

  const title = result ? t(`${P}result.${result.kind}.head`)
    : step === 2 ? t(`${P}titleReview`) : t(renew ? `${P}titleRenew` : `${P}titleIssue`)
  if (!open) return null
  return (
    <AtelierDialog title={title} subtitle={step === 1 && !result ? t(renew ? `${P}subtitleRenew` : `${P}subtitleIssue`) : undefined}
      size={result ? 'narrow' : 'wide'} onClose={() => changeOpen(false)} testId="issue-dialog">
      <>
        {result && (
          <Result result={result} t={t} inRouter={inRouter} canSeeApprovals={hasPermission('read:approvals')}
            onClose={close} onOpen={(issued) => { close(); onOpen?.(issued) }} />
        )}
        {!result && (
          <IssueCertificateForm
            mode={mode}
            certificate={certificate}
            cas={cas || loadedCas}
            initialData={initialData}
            canUseCsr={!renew && hasPermission('write:csrs')}
            onSubmit={async (...args) => { busy(true); try { return await submit(...args) } finally { busy(false) } }}
            onSent={sent}
            onCancel={close}
            onStepChange={setStep}
            reviewFocus={closeButton}
            t={t}
          />
        )}
      </>
    </AtelierDialog>
  )
}
