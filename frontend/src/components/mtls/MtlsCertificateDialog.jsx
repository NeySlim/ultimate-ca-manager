/**
 * Adding a client certificate for mutual TLS (an account's own, or a user's from the Users page),
 * in the mockup's dialog: the way it comes (`.segmented`), then the form of that way in
 * `.form-fields` and its actions under the rule. Generate: name, the issuing CA (the caller's
 * picker, absent without the right to choose one), validity; Import: name, PEM or a file;
 * Assign: one of the certificates the server offers, as the radio cards of exportDialog().
 * `result` replaces the form once a certificate is generated.
 */
import { useTranslation } from 'react-i18next'
import { AtelierDialog, Btn, SkeletonPanel } from '../atelier'
import { ChoiceField, Input, NumberInput, PemField, SegmentedField } from '../atelier/Form'
import { formatDate } from '../../lib/utils'

export function MtlsCertificateDialog({
  title, onClose, busy = false, canGenerate = true, tab, onTab,
  generateForm, setGenerateForm, namePlaceholder, caPicker, onGenerate,
  importForm, setImportForm, onImport,
  assign, onAssign, result,
}) {
  const { t } = useTranslation()
  const mode = tab === 'generate' && !canGenerate ? 'import' : tab
  const ways = [
    canGenerate && { value: 'generate', label: t('account.mtlsGenerate') },
    { value: 'import', label: t('account.mtlsImport') },
    { value: 'assign', label: t('account.mtlsAssign') },
  ].filter(Boolean)
  const cancel = <button type="button" className="btn" data-action="close-modal" onClick={onClose}>{t('common.cancel')}</button>
  const submit = (fn) => (e) => { e.preventDefault(); if (!busy) fn() }
  // The way heads each form's fields, so the mockup's gap of .form-fields falls between them
  const way = <SegmentedField id="mtls-way" label={t('account.mtlsWay')} options={ways} pressed={(v) => v === mode} onPick={onTab} />

  return (
    <AtelierDialog title={title} size="narrow" onClose={onClose} testId="mtls-dialog">
      {result || (
        <>
          {mode === 'generate' && (
            <form onSubmit={submit(onGenerate)} noValidate>
              <div className="form-fields">
                {way}
                <Input id="mtls-name" data-autofocus full label={t('account.mtlsCertName')} value={generateForm.name} placeholder={namePlaceholder}
                  onChange={(e) => setGenerateForm((prev) => ({ ...prev, name: e.target.value }))} />
                {caPicker}
                <NumberInput id="mtls-validity" label={t('account.mtlsValidityDays')} value={String(generateForm.validity_days ?? '')}
                  onChange={(e) => setGenerateForm((prev) => ({ ...prev, validity_days: e.target.value }))} />
              </div>
              <div className="modal-actions">
                {cancel}
                <Btn type="submit" tone="primary" icon="cert" disabled={busy || undefined}>{t('account.generateCertificate')}</Btn>
              </div>
            </form>
          )}
          {mode === 'import' && (
            <form onSubmit={submit(onImport)} noValidate>
              <div className="form-fields">
                {way}
                <Input id="mtls-import-name" data-autofocus full label={t('account.mtlsCertName')} value={importForm.name} placeholder={t('account.mtlsImportNamePlaceholder')}
                  onChange={(e) => setImportForm((prev) => ({ ...prev, name: e.target.value }))} />
                <PemField id="mtls-pem" label={t('account.mtlsPemData')} value={importForm.pem} accept=".pem,.crt,.cer" rows={6}
                  placeholder="-----BEGIN CERTIFICATE-----" fileLabel={t('account.mtlsOrUploadFile')}
                  onChange={(pem) => setImportForm((prev) => ({ ...prev, pem }))} />
              </div>
              <div className="modal-actions">
                {cancel}
                <Btn type="submit" tone="primary" icon="upload" disabled={busy || !importForm.pem.trim() || undefined}>{t('account.importCertificate')}</Btn>
              </div>
            </form>
          )}
          {mode === 'assign' && (
            <form onSubmit={submit(onAssign)} noValidate>
              <div className="form-fields">
                {way}
                {assign.loading ? (
                  <div className="field full"><SkeletonPanel label={t('common.loading')} /></div>
                ) : assign.certs.length === 0 ? (
                  <p className="field full muted small">{t('account.mtlsNoAvailableCerts')}</p>
                ) : (
                  <div className="field full compare-scroll">
                    <ChoiceField name="mtls-assign" legend={t('account.mtlsAssignChoice')} value={assign.selected ? String(assign.selected.id) : ''}
                      onChange={(id) => assign.onSelect(assign.certs.find((c) => String(c.id) === id))}
                      options={assign.certs.map((cert) => ({
                        value: String(cert.id),
                        label: cert.name,
                        hint: [cert.subject, cert.valid_to && t('account.mtlsExpiresOn', { date: formatDate(cert.valid_to) })].filter(Boolean).join(' · '),
                      }))} />
                  </div>
                )}
              </div>
              <div className="modal-actions">
                {cancel}
                <Btn type="submit" tone="primary" icon="link" disabled={busy || !assign.selected || undefined}>{t('account.assignCertificate')}</Btn>
              </div>
            </form>
          )}
        </>
      )}
    </AtelierDialog>
  )
}

export default MtlsCertificateDialog
