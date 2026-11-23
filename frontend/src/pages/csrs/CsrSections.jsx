/**
 * The sections of a request in the dock and in a detached window: Aperçu (properties, summary),
 * Détails (subject, alternative names), and the PEM while it waits. The page and the window
 * draw the same ones.
 */
import { useTranslation } from 'react-i18next'
import { Pill, Section, Facts } from '../../components/atelier'
import { certificateKeyLabel, serialHex } from '../../lib/certificateDetail'
import { signatureHashName } from '../../lib/signatureName'
import { dateOf } from '../admin/adminDates'
import { PemPanel } from '../certificates/inspector/PemPanel'

/** Signed: its state says so, or it comes from the signed list and is not pending. */
export const csrSigned = (row, fromHistory = false) => row.status === 'Signed' || (fromHistory && row.status !== 'Pending')
export const csrName = (t, row) => t('csrs.module.name', { id: row.id })
export const csrPill = (t, row, fromHistory = false) => (csrSigned(row, fromHistory)
  ? <Pill label={t('csrs.states.signed')} tone="good" />
  : <Pill label={t('csrs.states.pending')} tone="warn" />)
export const csrSubject = (t, row) => row.common_name || row.cn || row.subject || t('common.unnamed')
export const csrRequester = (row) => row.requester || row.created_by || '—'
export const csrKey = (row) => certificateKeyLabel(row) || '—'
/** The section tabs: a signed request has no PEM of its own to show. */
export const csrSections = (t, signed) => [['overview', t('atelier.overview')], ['details', t('csrs.module.details')], ...(signed ? [] : [['pem', 'PEM']])]

export function CsrSections({ csr, signed, section }) {
  const { t, i18n } = useTranslation()
  const locale = i18n?.language || 'en'
  const summary = signed
    ? t('csrs.module.signedSummary', { ca: csr.signed_by || csr.issuer_name || '—', date: dateOf(csr.signed_at || csr.valid_from, locale) || '—' })
    : (csr.descr || t('csrs.module.pendingSummary'))
  // A value the request has, else the absence in grey
  const serial = serialHex(csr.serial_number)
  const fact = (label, value) => (value ? [label, value] : { label, absent: '—' })
  const sans = csr.sans?.length ? csr.sans : (csr.san_combined ? csr.san_combined.split(',').map((s) => s.trim()).filter(Boolean) : [])
  return (
    <>
      {section === 'overview' && (
        <div className="module-detail">
          <Section title={t('atelier.properties')}>
            <Facts items={[
              [t('csrs.module.subject'), csrSubject(t, csr)],
              fact(t('csrs.module.requester'), csr.requester || csr.created_by),
              fact(t('csrs.module.key'), certificateKeyLabel(csr)),
              fact(t('csrs.module.submitted'), dateOf(csr.created_at, locale)),
              [t('atelier.state'), csrPill(t, csr, signed)],
              signed && fact(t('common.signedBy'), csr.signed_by || csr.issuer_name),
              signed && fact(t('common.expires'), dateOf(csr.valid_to, locale)),
              // A serial longer than a short value goes under its term in a narrow panel
              signed && serial && { label: t('common.serial'), value: serial, kind: 'hex', long: serial.length > 23 },
            ]} />
          </Section>
          <Section title={t('atelier.summary')}><p className="summary">{summary}</p></Section>
        </div>
      )}
      {section === 'details' && (
        <div className="module-detail">
          <Section title={t('common.subject')}>
            <Facts items={[
              fact(t('common.organization'), csr.organization),
              fact(t('common.orgUnit'), csr.organizational_unit),
              fact(t('common.country'), csr.country),
              fact(t('common.state'), csr.state),
              fact(t('common.locality'), csr.locality),
              fact(t('common.email'), csr.email),
              // Named by its hash, as a certificate's signature is
              fact(t('common.signature'), csr.signature_algorithm && signatureHashName(csr.signature_algorithm)),
            ]} />
          </Section>
          <Section title={t('common.subjectAltNames')}>
            {sans.length ? <ul className="record-list">{sans.map((s) => <li key={s}><div className="rl-main"><span className="mono">{s}</span></div></li>)}</ul>
              : <p className="muted small">{t('csrs.module.noSans')}</p>}
          </Section>
        </div>
      )}
      {section === 'pem' && !signed && <PemPanel cert={csr} />}
    </>
  )
}
