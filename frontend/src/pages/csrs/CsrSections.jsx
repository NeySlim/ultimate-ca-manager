/**
 * The sections of a request in the dock and in a detached window: Aperçu (properties, summary),
 * Détails (subject, alternative names), and the PEM while it waits. The page and the window
 * draw the same ones.
 */
import { useTranslation } from 'react-i18next'
import { Pill, Section, Props } from '../../components/atelier'
import { certificateKeyLabel, serialHex } from '../../lib/certificateDetail'
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
  const sans = csr.sans?.length ? csr.sans : (csr.san_combined ? csr.san_combined.split(',').map((s) => s.trim()).filter(Boolean) : [])
  return (
    <>
      {section === 'overview' && (
        <div className="module-detail">
          <Section title={t('atelier.properties')}>
            <Props items={[
              [t('csrs.module.subject'), csrSubject(t, csr)],
              [t('csrs.module.requester'), csrRequester(csr)],
              [t('csrs.module.key'), csrKey(csr)],
              [t('csrs.module.submitted'), dateOf(csr.created_at, locale) || '—'],
              [t('atelier.state'), csrPill(t, csr, signed)],
              signed && [t('common.signedBy'), csr.signed_by || csr.issuer_name || '—'],
              signed && [t('common.expires'), dateOf(csr.valid_to, locale) || '—'],
              signed && csr.serial_number && [t('common.serial'), <span key="serial" className="mono">{serialHex(csr.serial_number)}</span>],
            ]} />
          </Section>
          <Section title={t('atelier.summary')}><p className="summary">{summary}</p></Section>
        </div>
      )}
      {section === 'details' && (
        <div className="module-detail">
          <Section title={t('common.subject')}>
            <Props items={[
              [t('common.organization'), csr.organization || '—'],
              [t('common.orgUnit'), csr.organizational_unit || '—'],
              [t('common.country'), csr.country || '—'],
              [t('common.state'), csr.state || '—'],
              [t('common.locality'), csr.locality || '—'],
              [t('common.email'), csr.email || '—'],
              [t('common.signature'), csr.signature_algorithm || '—'],
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
