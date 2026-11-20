/**
 * The dialog around IssueCertificateForm, for an issuance (Certificates page) or a renewal
 * (inspector): it sends the reviewed request and says what came of it. A request that a
 * policy holds for approval is told in the Review step; the dialog then stays open.
 */
import { useCallback, useEffect, useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { X } from '@phosphor-icons/react'
import { useTranslation } from 'react-i18next'
import { certificatesService, csrsService, casService } from '../../services'
import { useNotification } from '../../contexts'
import { usePermission } from '../../hooks'
import { issueWithSubjectOverride } from '../../lib/uniqueSubject'
import { showNotices } from '../../lib/notices'
import { IssueCertificateForm } from './IssueCertificateForm'
import './issue/issue.css'

const P = 'certificates.issueForm.'

/**
 * @param {object} p
 * @param {boolean} p.open
 * @param {(open: boolean) => void} p.onOpenChange
 * @param {'issue'|'renew'} [p.mode]
 * @param {object} [p.certificate]  the certificate a renewal starts from
 * @param {object[]} [p.cas]  the CAs to choose from; loaded here when absent
 * @param {object} [p.initialData]  a prefill (re-key from a CSR)
 * @param {(issued: object|null) => void} [p.onIssued]  after a certificate was issued or renewed
 * @param {() => void} [p.onMutate]  just before a mutating request
 */
export function IssueCertificateDialog({ open, onOpenChange, mode = 'issue', certificate = null, cas, initialData, onIssued, onMutate }) {
  const { t } = useTranslation()
  const { showSuccess, showWarning, showConfirm } = useNotification()
  const { hasPermission } = usePermission()
  const [step, setStep] = useState(1)
  const [loadedCas, setLoadedCas] = useState([])
  // One upload per CSR text: a retry after a refused signature signs the request already uploaded
  const [uploaded, setUploaded] = useState({ pem: null, id: null })
  const renew = mode === 'renew'

  useEffect(() => {
    if (!open || cas || renew) return undefined
    let cancelled = false
    casService.getAll().then((res) => { if (!cancelled) setLoadedCas(res?.data || []) }).catch(() => {})
    return () => { cancelled = true }
  }, [open, cas, renew])
  useEffect(() => { if (!open) setStep(1) }, [open])

  const close = () => onOpenChange(false)

  // The form names its operation; without it, the dialog's mode decides
  const submit = useCallback(async (body, { kind = renew ? 'renew' : 'issue', csr } = {}) => {
    onMutate?.()
    if (kind === 'renew') {
      const res = await certificatesService.renew(certificate.id, body)
      if (res?.data?.approval_required) return { approval: res.data.policy_name ?? '' }
      if (res?.meta?.msca_status === 'pending') showSuccess(t('certificates.renewPendingMsca'))
      else {
        const related = res?.data?.related_renewed
        showSuccess(related?.length
          ? t('certificates.hybrid.renewedWithRelated', { id: related.join(', #') })
          : t('certificates.renewed'))
        showNotices(res, showWarning)
      }
      close()
      onIssued?.(res?.data || null)
      return undefined
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
    if (response?.data?.approval_required) return { approval: response.data.policy_name ?? '' }
    // A hybrid pair answers { certificate: classical, related: ML-DSA }
    const pair = response?.data?.certificate ? response.data : null
    const issued = pair ? pair.certificate : response?.data
    showSuccess(pair
      ? t('certificates.hybrid.pairIssued', { classical: pair.certificate.id, pq: pair.related?.id })
      : t('messages.success.create.certificate'))
    showNotices(response, showWarning)
    close()
    onIssued?.(issued?.id ? issued : null)
    return undefined
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [renew, certificate, uploaded, onIssued, onMutate, t])

  const title = step === 2 ? t(`${P}titleReview`) : t(renew ? `${P}titleRenew` : `${P}titleIssue`)
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="iss-overlay" />
        <Dialog.Content className="iss-dialog" aria-describedby={step === 1 ? 'iss-subtitle' : undefined}
          onOpenAutoFocus={(e) => {
            // The first field takes the focus, as in the Atelier, not the close button
            e.preventDefault()
            e.currentTarget.querySelector('.iss-body select, .iss-body input')?.focus()
          }}>
          <header className="iss-head">
            <div>
              <Dialog.Title asChild><h2>{title}</h2></Dialog.Title>
              {step === 1 && <p id="iss-subtitle">{t(renew ? `${P}subtitleRenew` : `${P}subtitleIssue`)}</p>}
            </div>
            <Dialog.Close className="iss-icon-btn is-quiet" aria-label={t(`${P}close`)}>
              <X aria-hidden="true" />
            </Dialog.Close>
          </header>
          <div className="iss-body">
            {open && (
              <IssueCertificateForm
                mode={mode}
                certificate={certificate}
                cas={cas || loadedCas}
                initialData={initialData}
                canUseCsr={!renew && hasPermission('write:csrs')}
                onSubmit={submit}
                onCancel={close}
                onStepChange={setStep}
                t={t}
              />
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
