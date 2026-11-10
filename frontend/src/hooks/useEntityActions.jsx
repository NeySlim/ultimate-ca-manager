/**
 * useEntityActions: every action of a certificate, CA or trust store entry
 * (export, revoke, renew, delete, offline...) and the modals they open.
 * The detail window and the page slide-overs render the same list.
 *
 * Returns { actions, modals, refresh, handler }. `actions` is the ordered
 * list { id, label, icon, onClick, visible, disabled, danger }; `modals` is a
 * fragment to render once; `handler(id)` gives a visible action's callback.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Certificate, ShieldCheck, Trash, X, ArrowsClockwise, ShieldWarning, PushPin,
  SealCheck, Vault, PencilSimple, Key,
} from '@phosphor-icons/react'
import { useNotification } from '../contexts'
import { usePermission } from './index'
import { ExportModal } from '../components/ExportModal'
import { CertificateLintModal } from '../components/CertificateLintModal'
import { KeyRecoveryRequestModal } from '../components/KeyRecoveryRequestModal'
import { RevokeCertificateModal } from '../components/RevokeCertificateModal'
import { TakeOfflineModal } from '../components/cas/TakeOfflineModal'
import { RestoreModal } from '../components/cas/RestoreModal'
import { ImportCaKeyModal } from '../components/cas/ImportCaKeyModal'
import { UploadCACertModal } from '../pages/cas/UploadCACertModal'
import { certificatesService, casService, userCertificatesService } from '../services'
import { ENTITY_RESOURCE, entityService, entityTitle } from '../lib/entityDetail'
import { isOnHold, downloadBlob } from '../lib/utils'
import { holdsNoKey } from '../lib/caSelection'
import { canExportPrivateKey } from '../lib/exportPermissions'
import { downloadExport } from '../lib/exportDownload'
import { askRenewal } from '../lib/renewalPrompt'
import { renameCertificate } from '../lib/certificateRename'
import { showNotices } from '../lib/notices'

// Entity type -> messages.confirm.delete.* key; every locale defines these
const CONFIRM_DELETE_KEY = { certificate: 'certificate', user_certificate: 'certificate', ca: 'ca', truststore: 'truststore' }

/**
 * @param {object} p
 * @param {string} p.type  certificate | ca | truststore | user_certificate
 * @param {object} p.entity  the loaded entity
 * @param {*} [p.entityId]  id the routes take when it differs from entity.id
 * @param {(updated: object) => void} [p.onChanged]  entity replaced in place
 * @param {() => void} [p.onClose]  the surface showing the entity should go away
 * @param {() => void} [p.onMutate]  called just before a mutating request
 * @param {object} [p.permissions]  { canWrite, canDelete, hasPermission } override
 * @param {Function} [p.t]  translator override
 */
export function useEntityActions({ type, entity, entityId, onChanged, onClose, onMutate, permissions, t: tOverride }) {
  const { t: hookT } = useTranslation()
  const t = tOverride || hookT
  const { showSuccess, showError, showConfirm, showPrompt, showWarning } = useNotification()
  const ambient = usePermission()
  const { canWrite, canDelete, hasPermission } = { ...ambient, ...permissions }

  const [exportOpen, setExportOpen] = useState(false)
  const [lintOpen, setLintOpen] = useState(false)
  const [keyRecoveryOpen, setKeyRecoveryOpen] = useState(false)
  const [revokeOpen, setRevokeOpen] = useState(false)
  const [revoking, setRevoking] = useState(false)
  const [offlineOpen, setOfflineOpen] = useState(false)
  const [restoreOpen, setRestoreOpen] = useState(false)
  const [importKeyOpen, setImportKeyOpen] = useState(false)
  const [uploadCertOpen, setUploadCertOpen] = useState(false)
  // The operator asked to delete a still-valid certificate and accepted to
  // revoke it first; the deletion resumes once the revocation is through.
  const [deleteAfterRevoke, setDeleteAfterRevoke] = useState(false)

  const id = entityId ?? entity?.id
  const resource = ENTITY_RESOURCE[type] || 'certificates'
  const data = entity
  const isCert = type === 'certificate'
  const isUserCert = type === 'user_certificate'
  const isCA = type === 'ca'
  const onHold = isOnHold(data)
  const title = data ? entityTitle(type, data, t) : ''

  const refresh = (changedType = type) =>
    window.dispatchEvent(new CustomEvent('ucm:data-changed', { detail: { type: changedType } }))
  const close = () => onClose?.()

  const handleExport = async (format = 'pem', options = {}) => {
    try {
      const name = data?.cn || data?.common_name || data?.name || type
      await downloadExport(entityService(type).export(id, format, options), { format, name })
      showSuccess(t('common.exported'))
    } catch (err) {
      // The server's refusal says why (a bundle member without a key); a network failure does not
      showError(err?.status ? err.message : t('common.exportFailed'))
    }
  }

  const handleRevokeConfirm = async (reason, options) => {
    setRevokeOpen(false)
    setRevoking(true)
    try {
      onMutate?.()
      let queued = null
      if (isCA) {
        // Intermediate CA revoked from its parent (#343)
        const res = await casService.revoke(id, { reason })
        if (res?.data?.approval_required) queued = t('cas.revocationApprovalRequired', { policy: res.data.policy_name })
        else showSuccess(t('cas.revokeSuccess', 'CA revoked'))
        // The parent could not publish the revocation (offline parent, CDP off)
        const revoked = res?.data || res
        const codes = revoked?.warning_codes || []
        if (codes.length) codes.forEach(code => showWarning(t(`cas.revokeWarnings.${code}`)))
        else for (const w of revoked?.warnings || []) showWarning(w)
        if (!queued && revoked?.id) onChanged?.({ ...data, ...revoked })
      } else if (isUserCert) {
        // id is the enrolment id, which only this route resolves; the
        // certificates route would look it up in a different table.
        const res = await userCertificatesService.revoke(id, reason)
        if (res?.data?.approval_required) queued = t('certificates.revocationApprovalRequired', { policy: res.data.policy_name })
        else showSuccess(t('messages.success.other.revoked'))
      } else {
        const res = await certificatesService.revoke(id, reason, options)
        const relatedRevoked = res?.data?.related_revoked
        if (res?.data?.approval_required) queued = t('certificates.revocationApprovalRequired', { policy: res.data.policy_name })
        else {
          showSuccess(relatedRevoked != null
            ? t('revocation.revokedWithRelated', { id: relatedRevoked })
            : t('messages.success.other.revoked'))
          if (res?.data?.related_not_revoked != null) {
            showWarning(t('revocation.relatedRevokeFailed', { id: res.data.related_not_revoked }))
          } else if (options?.revokeRelated && relatedRevoked == null) showWarning(t('revocation.relatedNotRevoked'))
        }
      }
      if (queued) {
        // Held by a revocation policy: nothing was revoked, so nothing is deleted
        showWarning(queued)
        setDeleteAfterRevoke(false)
      } else if (deleteAfterRevoke) {
        setDeleteAfterRevoke(false)
        try {
          await entityService(type).delete(id)
          showSuccess(t('common.deleted'))
        } catch (err) {
          showError(err.message || t('common.deleteFailed'))
        }
      }
      refresh()
      close()
    } catch (err) {
      showError(err.message || (isCA ? t('cas.revokeFailed', 'Failed to revoke CA') : t('messages.errors.revokeFailed.certificate')))
    } finally {
      setRevoking(false)
    }
  }

  const handleUnhold = async () => {
    const confirmed = await showConfirm(
      t('certificates.unholdWarning', 'This will remove the certificate hold and restore it to valid status. The certificate will be removed from the CRL.'),
      {
        title: t('certificates.unholdCertificate', 'Remove Certificate Hold'),
        confirmText: t('certificates.unholdCertificate', 'Remove Hold'),
        variant: 'warning'
      }
    )
    if (!confirmed) return
    try {
      onMutate?.()
      await certificatesService.unhold(id)
      showSuccess(t('certificates.unheld', 'Certificate hold removed'))
      refresh()
      close()
    } catch (err) {
      showError(err.message || t('certificates.unholdFailed', 'Failed to remove hold'))
    }
  }

  const handleRenew = async () => {
    const body = await askRenewal(data, { showPrompt, showConfirm, showError, t })
    if (!body) return
    try {
      onMutate?.()
      const res = await certificatesService.renew(id, body)
      if (res?.data?.approval_required) {
        showWarning(t('certificates.approvalRequired', { policy: res.data.policy_name }))
      } else if (res?.meta?.msca_status === 'pending') {
        showSuccess(t('certificates.renewPendingMsca'))
      } else {
        const relatedRenewed = res?.data?.related_renewed
        showSuccess(relatedRenewed?.length
          ? t('certificates.hybrid.renewedWithRelated', { id: relatedRenewed.join(', #') })
          : t('certificates.renewed'))
        showNotices(res, showWarning)
      }
      refresh()
      close()
    } catch (err) {
      showError(err?.message || t('common.operationFailed'))
    }
  }

  const handleRename = async () => {
    const updated = await renameCertificate(data, { showPrompt, showSuccess, showError, t })
    if (!updated) return
    onChanged?.({ ...data, ...updated })
    refresh()
  }

  const handleDelete = async () => {
    // The guard sits here as well as on the button: a surface that offers the
    // action anyway still cannot reach a route that would refuse it.
    if (!canDelete(resource)) return
    // A certificate still trusted by relying parties has to be revoked first,
    // or it leaves UCM while staying valid everywhere else. Say so here rather
    // than let the route refuse afterwards, and offer to do both.
    const status = data?.revoked ? 'revoked' : data?.status
    if ((isCert || isUserCert) && data && status !== 'revoked' && status !== 'expired') {
      const revokeFirst = await showConfirm(t('certificates.deleteNeedsRevoke'), {
        title: t('common.deleteCertificate'),
        confirmText: t('certificates.revokeThenDelete'),
        variant: 'danger'
      })
      if (!revokeFirst) return
      setDeleteAfterRevoke(true)
      setRevokeOpen(true)
      return
    }
    const confirmed = await showConfirm(
      t(`messages.confirm.delete.${CONFIRM_DELETE_KEY[type] || 'generic'}`),
      {
        title: t('common.confirmDelete', 'Confirm Delete'),
        confirmText: t('common.delete', 'Delete'),
        variant: 'danger'
      }
    )
    if (!confirmed) return
    try {
      onMutate?.()
      await entityService(type).delete(id)
      showSuccess(t('common.deleted'))
      refresh()
      close()
    } catch (err) {
      showError(err.message || t('common.deleteFailed'))
    }
  }

  const handleKeyImported = (updated) => {
    if (updated?.id) onChanged?.(updated)
    refresh('ca')
  }

  const handleManagePins = () => {
    window.dispatchEvent(new CustomEvent('ucm:open-pins-modal', { detail: { caId: id } }))
  }

  // External-CSR CA lifecycle (#298)
  const handleDownloadCsr = async () => {
    try {
      const blob = await casService.downloadCsr(id)
      const name = (data?.common_name || data?.descr || 'ca').replace(/[^a-zA-Z0-9._-]+/g, '_')
      downloadBlob(blob, `${name}.csr`)
    } catch (err) {
      showError(err?.message || t('cas.csrDownloadFailed', 'Failed to download CSR'))
    }
  }

  const handleRenewCsr = async () => {
    try {
      await casService.renewCsr(id)
      showSuccess(t('cas.csrDownloadStarted', 'CSR generated: download started'))
      refresh('ca')
      await handleDownloadCsr()
      close()
    } catch (err) {
      showError(err?.message || t('cas.csrDownloadFailed', 'Failed to download CSR'))
    }
  }

  const hasPrivateKey = !!data?.has_private_key
  const external = isCA && data?.imported_from === 'external_csr'
  const lintable = isCert || isUserCert
  const row = (spec) => ({ disabled: false, danger: false, inBar: true, tone: 'primary', ...spec })

  const actions = data ? [
    // Hidden for a pending external-CSR CA: there is nothing to export yet
    row({ id: 'export', label: t('export.title', 'Export'), icon: Certificate,
      onClick: () => setExportOpen(true), visible: !(isCA && data.pending) }),
    row({ id: 'downloadCsr', label: t('cas.downloadCsr', 'Download CSR'), icon: Certificate,
      onClick: handleDownloadCsr, visible: isCA && !!data.has_csr }),
    row({ id: 'uploadCertificate', label: t('cas.uploadCertificate', 'Upload certificate'), icon: ShieldCheck, tone: 'success',
      onClick: () => setUploadCertOpen(true),
      visible: isCA && canWrite('cas') && external && (data.pending || data.has_csr) && !data.offline }),
    row({ id: 'renewCsr', label: t('cas.renewViaCsr', 'Renew via CSR'), icon: ArrowsClockwise, tone: 'success',
      onClick: handleRenewCsr,
      visible: isCA && canWrite('cas') && external && !data.pending && !data.offline && !data.revoked }),
    row({ id: 'lint', label: t('lint.action', 'Lint'), icon: SealCheck,
      onClick: () => setLintOpen(true), visible: lintable }),
    row({ id: 'keyRecovery', label: t('keyRecovery.requestShort', 'Recover key'), icon: Vault,
      onClick: () => setKeyRecoveryOpen(true),
      visible: lintable && hasPrivateKey && hasPermission('write:key_recovery') }),
    row({ id: 'pins', label: t('templates.managePins', 'Manage Pins'), icon: PushPin,
      onClick: handleManagePins,
      visible: isCA && canWrite('cas') && canWrite('templates') && !data.pending }),
    row({ id: 'rename', label: t('certificates.rename', 'Rename'), icon: PencilSimple,
      onClick: handleRename, visible: isCert && canWrite('certificates') }),
    row({ id: 'renew', label: t('common.renew', 'Renew'), icon: ArrowsClockwise, tone: 'success',
      onClick: handleRenew,
      visible: isCert && canWrite('certificates') && !data.revoked && (data.has_private_key || data.source === 'msca') }),
    row({ id: 'revoke', label: isCA ? t('cas.revoke', 'Revoke CA') : t('common.revoke', 'Revoke'), icon: X, iconWeight: 'bold', tone: 'warning',
      onClick: () => setRevokeOpen(true),
      // A certificate on hold can still be revoked for good (RFC 5280 §5.2.4);
      // a CA is revoked by its parent, so it needs one held in UCM (#343)
      visible: ((isCert || isUserCert) && canWrite(resource) && (!data.revoked || onHold))
        || (isCA && canWrite('cas') && !data.revoked && !data.revoked_in_chain && !data.pending
          && !data.is_root && data.type !== 'root' && !!data.parent_id) }),
    row({ id: 'unhold', label: t('certificates.removeHold', 'Remove Hold'), icon: ArrowsClockwise, tone: 'success',
      onClick: handleUnhold, visible: isCert && canWrite('certificates') && onHold }),
    // Offline needs the key in UCM's own store, and a revoked CA stays visibly revoked (#348)
    row({ id: 'offline', label: t('cas.takeOffline', 'Take Offline'), icon: ShieldWarning, tone: 'warning',
      onClick: () => setOfflineOpen(true),
      visible: isCA && canWrite('cas') && !data.offline && !data.pending && !data.revoked
        && data.has_private_key && !data.uses_hsm }),
    row({ id: 'restore', label: t('cas.restore', 'Restore'), icon: ArrowsClockwise, tone: 'success',
      onClick: () => setRestoreOpen(true), visible: isCA && canWrite('cas') && !!data.offline }),
    // Rendered by the CA panel's "no key" banner, not by the action bar
    row({ id: 'importKey', label: t('cas.importPrivateKey', 'Import private key'), icon: Key, inBar: false,
      onClick: () => setImportKeyOpen(true), visible: isCA && canWrite('cas') && holdsNoKey(data) }),
    row({ id: 'delete', label: t('common.delete'), icon: Trash, danger: true, iconOnly: true, end: true,
      onClick: handleDelete, visible: canDelete(resource) }),
  ] : []

  const handler = (actionId) => {
    const a = actions.find(x => x.id === actionId)
    return a && a.visible && !a.disabled ? a.onClick : null
  }

  const modals = data ? (
    <>
      <ExportModal
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        entityType={isCA ? 'ca' : 'certificate'}
        entityName={title}
        hasPrivateKey={isCA ? hasPrivateKey && !data.uses_hsm : hasPrivateKey}
        isHsmBacked={isCA ? !!data.uses_hsm : undefined}
        keyAlgorithm={data.key_algorithm || data.key_type}
        // Each type has its own server-side key gate (lib/exportPermissions);
        // write access to the resource was never one of them for a certificate.
        canExportKey={canExportPrivateKey(type, { hasPermission, canWrite, usesHsm: !!data.uses_hsm })}
        onExport={handleExport}
        chainVariantsFor={isCA || isCert ? { type: isCA ? 'ca' : 'certificate', id } : undefined}
        relatedCertificateId={isCert ? (data.related_certificate_id ?? null) : null}
      />
      {lintable && (
        <CertificateLintModal certId={id} certName={title} open={lintOpen} onClose={() => setLintOpen(false)} />
      )}
      {(isCert || isUserCert || isCA) && (
        <RevokeCertificateModal
          allowHold={!isCA && !onHold}
          open={revokeOpen}
          onClose={() => { setRevokeOpen(false); setDeleteAfterRevoke(false) }}
          onConfirm={handleRevokeConfirm}
          certificate={data}
          loading={revoking}
          title={isCA ? t('cas.revoke', 'Revoke CA') : undefined}
          warning={isCA ? t('cas.revokeWarning') : undefined}
        />
      )}
      {lintable && (
        <KeyRecoveryRequestModal certId={id} certName={title} open={keyRecoveryOpen} onClose={() => setKeyRecoveryOpen(false)} />
      )}
      {isCA && (
        <>
          <ImportCaKeyModal open={importKeyOpen} onClose={() => setImportKeyOpen(false)} ca={data} onSuccess={handleKeyImported} t={t} />
          <TakeOfflineModal open={offlineOpen} onClose={() => setOfflineOpen(false)} ca={data} onSuccess={close} />
          <RestoreModal open={restoreOpen} onClose={() => setRestoreOpen(false)} ca={data} onSuccess={close} />
          <UploadCACertModal open={uploadCertOpen} onClose={() => setUploadCertOpen(false)} ca={data} onSuccess={close} />
        </>
      )}
    </>
  ) : null

  return { actions, modals, refresh, handler }
}
