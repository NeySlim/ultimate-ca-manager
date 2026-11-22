/**
 * The dock of an order of the ACME client: domains, order facts, the pending challenge (the TXT
 * record, or the HTTP-01 URL and file), the error, and every action the order allows (verify,
 * check, finalize, view, download, renew, automatic renewal, delete).
 */
import { useTranslation } from 'react-i18next'
import { Btn, Dock, DockBody, Section, Facts, Pill } from '../../components/atelier'
import { downloadBlob } from '../../lib/utils'
import { stateLabel } from '../../lib/stateLabel'
import { dateTimeOf } from '../admin/adminDates'
import { Notice } from '../protocols/atelierParts'
import { copyRow, factRow } from '../protocols/factRows'
import { http01Url } from '../protocols/protocolStates'

const ORDER_TONES = { valid: 'good', issued: 'good', ready: 'good', pending: 'warn', processing: 'warn', validating: 'warn', invalid: 'bad' }

export default function OrderDetailPanel({ order, onClose, onDownloadCert, onViewCertificate, onRenewCertificate, onVerifyChallenge, onCheckOrderStatus,
  onFinalizeOrder, onDeleteOrder, onToggleRenewal, canWrite = false, canDelete = false }) {
  const { t, i18n } = useTranslation()
  const locale = i18n?.language || 'en'
  const name = order.primary_domain || order.domains?.[0] || t('common.unknown')
  const status = String(order.status || '').toLowerCase()
  const proxy = order.is_proxy_order
  const pill = <Pill label={stateLabel(t, order.status)} tone={ORDER_TONES[status] || 'muted'} />
  const issued = status === 'issued' || (status === 'valid' && (order.certificate_id || order.error_message))

  return (
    <Dock label={t('atelier.detailOf', { name: t('acme.letsEncryptOrders') })} tabsLabel={t('atelier.openItem')} activeKey={order.id}
      tabs={[{ key: order.id, title: name, icon: 'refresh' }]} onClose={onClose}>
      <DockBody icon="refresh" title={name} badge={pill} section="order" onSection={() => {}}
        sectionsLabel={t('atelier.sectionsOf', { name })} sections={[['order', t('acme.orderInfo')]]}
        actions={<>
          {!proxy && canWrite && ['pending', 'processing'].includes(status) && <Btn tone="primary" icon="send" id="acme-order-verify" onClick={() => onVerifyChallenge(order)}>{t('acme.verifyChallenge')}</Btn>}
          {!proxy && canWrite && status === 'validating' && <>
            <Btn icon="search" onClick={() => onCheckOrderStatus(order)}>{t('acme.checkStatus')}</Btn>
            <Btn icon="send" onClick={() => onVerifyChallenge(order)}>{t('acme.retryVerification')}</Btn>
          </>}
          {!proxy && canWrite && ['ready', 'processing'].includes(status) && <Btn icon="check" onClick={() => onFinalizeOrder(order)}>{t('acme.finalize')}</Btn>}
          {order.certificate_id && <Btn icon="eye" onClick={() => onViewCertificate(order)}>{t('common.viewCertificate')}</Btn>}
          {!proxy && canWrite && issued && <Btn icon="refresh" write onClick={() => onRenewCertificate(order)}>{t('acme.renewNow')}</Btn>}
          {canDelete && <Btn icon="close" id="acme-order-delete" onClick={() => onDeleteOrder(order)}>{t('common.delete')}</Btn>}
        </>}>
        <div className="module-detail">
          <Section title={t('acme.orderInfo')}>
            <Facts items={[
              { label: t('acme.domains'), value: (order.domains || []).join(', ') || name, long: (order.domains || []).length > 1 },
              [t('acme.environment'), t(order.environment === 'production' ? 'acme.production' : 'acme.staging')],
              factRow(t('acme.method'), order.challenge_type?.toUpperCase()),
              [t('acme.provider'), order.dns_provider_name || t('acme.manualDns')],
              order.is_proxy_order && (order.account_email || order.account_short_id) && [t('acme.account'), order.account_email || `${order.account_short_id}…`],
              [t('atelier.state'), pill],
              factRow(t('common.created'), dateTimeOf(order.created_at, locale)),
              order.expires_at && [t('common.expires'), dateTimeOf(order.expires_at, locale)],
              order.renewal_failures > 0 && {
                label: t('acme.renewalFailuresLabel'), value: t('acme.renewalFailures', { count: order.renewal_failures }),
                sub: order.last_error_at ? t('acme.renewalLastFailure', { date: dateTimeOf(order.last_error_at, locale) }) : undefined,
              },
            ]} />
            {order.error_message && <Notice tone="bad" role="alert">{order.error_message}</Notice>}
            {order.renewal_retry_daily && <Notice tone="warn">{t('acme.renewalRetryDaily')}</Notice>}
            {proxy && <Notice>{t('acme.proxyOrderClientDriven')}</Notice>}
            {!proxy && !order.opened_by_renewal && onToggleRenewal && (
              <label className="checkbox-line">
                <input type="checkbox" checked={order.renewal_enabled !== false} disabled={!canWrite || undefined} onChange={(e) => onToggleRenewal(order, e.target.checked)} />
                {t('acme.orderAutoRenew')}
              </label>
            )}
          </Section>
          {status === 'pending' && order.challenges && (
            <Section title={t('acme.pendingChallenge')}>
              {order.challenge_type === 'http-01' && <p className="muted small">{t('acme.http01Hint')}</p>}
              {Object.entries(order.challenges).map(([domain, data]) => (
                <div key={domain} className="acme-challenge">
                  <Facts items={[
                    [t('acme.domain'), domain],
                    ...(order.challenge_type === 'dns-01' ? [
                      copyRow(t('acme.dnsRecordName'), data.dns_txt_name || data.record_name, undefined, { long: true }),
                      copyRow(t('acme.dnsRecordValue'), data.dns_txt_value || data.record_value, undefined, { long: true }),
                    ] : []),
                    ...(order.challenge_type === 'http-01' && data.token && data.key_authorization ? [
                      copyRow(t('acme.http01Url'), http01Url(domain, data), 'url'),
                      copyRow(t('acme.http01FileContent'), data.key_authorization, undefined, { long: true }),
                    ] : []),
                  ]} />
                  {order.challenge_type === 'http-01' && data.token && data.key_authorization && (
                    <div className="copy-url">
                      <Btn icon="download" onClick={() => downloadBlob(new Blob([data.key_authorization], { type: 'application/octet-stream' }), data.token)}>{t('acme.http01DownloadFile')}</Btn>
                    </div>
                  )}
                </div>
              ))}
            </Section>
          )}
          {order.certificate_id && (
            <Section title={t('acme.certificateActions')}>
              <div className="copy-url">
                <Btn icon="download" onClick={() => onDownloadCert(order, 'pem', false)}>{t('acme.downloadCert')}</Btn>{' '}
                <Btn icon="key" onClick={() => onDownloadCert(order, 'pem', true)}>{t('acme.downloadWithKey')}</Btn>
              </div>
            </Section>
          )}
        </div>
      </DockBody>
    </Dock>
  )
}
