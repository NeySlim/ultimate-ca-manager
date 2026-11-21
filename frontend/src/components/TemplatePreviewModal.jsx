/**
 * TemplatePreviewModal: what a certificate issued from this template would carry, in the mockup's
 * modal(): the notice, then the sample in the review-summary of the issue form (dl.props), its restrictions as pills.
 */
import { Fragment } from 'react'
import { useTranslation } from 'react-i18next'
import { AtelierDialog, Icon, Pill } from './atelier'
import { VALIDITY } from '../constants/config'
import { algorithmName, findAlgorithm } from '../lib/keyAlgorithms'

const SAN_SAMPLES = {
  dns: 'DNS: server.example.com',
  ip: 'IP: 192.0.2.10',
  email: 'Email: admin@example.com',
  uri: 'URI: https://example.com/',
  upn: 'UPN: user@example.com',
}

// The SAN types issuance holds the template to: [] when it does not enforce them
export function templateSanTypes(template) {
  if (!template?.enforce_san_types) return []
  let ext = template?.extensions_template
  if (typeof ext === 'string') {
    try { ext = JSON.parse(ext) } catch { ext = null }
  }
  return Array.isArray(ext?.san_types) ? ext.san_types : []
}

function SANPreview({ template, t }) {
  const types = templateSanTypes(template).filter(type => SAN_SAMPLES[type])
  return types.length ? types.map(type => SAN_SAMPLES[type]).join('\n') : t('templates.sanTypesAny')
}

export function TemplatePreviewModal({ open, onClose, template }) {
  const { t } = useTranslation()
  if (!open || !template) return null

  // Calculate sample validity dates
  const now = new Date()
  const validFrom = now.toISOString().split('T')[0]
  const validityDays = template.validity_days || VALIDITY.TEMPLATE_DEFAULT_DAYS
  const validTo = new Date(now.getTime() + validityDays * 24 * 60 * 60 * 1000).toISOString().split('T')[0]

  // A template stores a registry label ('RSA-2048', 'EC-P384', 'ML-DSA-65')
  const keyRow = findAlgorithm(template.key_type)
  const keyDisplay = keyRow ? algorithmName(keyRow, t) : (template.key_type || '—')
  const list = (v) => (Array.isArray(v) ? v.join(', ') : v)
  const rows = [
    [t('templates.commonName'), template.default_cn || template.allow_any_cn ? 'your-common-name.domain.com' : t('templates.fixedCN')],
    [t('templates.template'), template.name],
    [t('common.keyAlgorithm'), keyDisplay],
    [t('common.validityPeriod'), `${t('templates.validityDays', { count: validityDays })} (${validFrom} → ${validTo})`],
    template.key_usage && [t('common.keyUsage'), list(template.key_usage)],
    template.extended_key_usage && [t('common.extKeyUsage'), list(template.extended_key_usage)],
    [t('common.subjectAltNames'), <span className="mono" style={{ whiteSpace: 'pre-line' }}>{SANPreview({ template, t })}</span>],
  ].filter(Boolean)
  const restricted = template.max_path_length !== undefined || template.require_cn || !template.allow_any_cn

  return (
    <AtelierDialog title={t('templates.preview')} subtitle={`${t('templates.previewFor')}: ${template.name}`} onClose={onClose} testId="template-preview-dialog">
      <p className="notice"><Icon name="eye" /><span>{t('templates.previewDescription')}</span></p>
      <div className="review-summary">
        <h3>{t('templates.sampleCertificate')} <Pill tone="good" label={t('common.valid')} /></h3>
        <dl className="props">
          {rows.map(([k, v]) => <Fragment key={k}><dt>{k}</dt><dd>{v || '—'}</dd></Fragment>)}
        </dl>
      </div>
      {restricted && (
        <section style={{ marginTop: 18 }}>
          <h3 className="section-title">{t('templates.restrictions')}</h3>
          <div className="ca-badges">
            {!template.allow_any_cn && <Pill tone="warn" label={t('templates.fixedCN')} />}
            {template.require_cn && <Pill tone="muted" label={t('templates.cnRequired')} />}
            {template.max_path_length !== undefined && template.max_path_length >= 0 && <Pill tone="muted" label={`${t('common.pathLength')}: ${template.max_path_length}`} />}
            {template.basic_constraints === 'ca' && <Pill tone="muted" label={t('common.caCertificate')} />}
          </div>
        </section>
      )}
      <div className="modal-actions">
        <button type="button" className="btn primary" data-action="close-modal" data-write="false" onClick={onClose}>{t('common.close')}</button>
      </div>
    </AtelierDialog>
  )
}
