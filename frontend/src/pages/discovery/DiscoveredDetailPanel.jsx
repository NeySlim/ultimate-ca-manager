import { useState, useEffect, Fragment } from 'react'
import { useTranslation } from 'react-i18next'
import {
  ShieldCheck, Warning, WarningCircle, IdentificationBadge, Stamp
} from '@phosphor-icons/react'
import {
  Badge,
  CompactSection, CompactGrid, CompactField,
  CertificateExtensions, SubjectAltNames
} from '../../components'
import { discoveryService } from '../../services'
import { formatDate, extractCN } from '../../lib/utils'

// OID-to-i18n-key mapping for DN fields
const DN_LABEL_KEYS = {
  'CN': 'common.dnFields.cn',
  'O': 'common.dnFields.o',
  'OU': 'common.dnFields.ou',
  'L': 'common.dnFields.l',
  'ST': 'common.dnFields.st',
  'C': 'common.dnFields.c',
  'SN': 'common.dnFields.sn',
  'GN': 'common.dnFields.gn',
  'DC': 'common.dnFields.dc',
  '1.2.840.113549.1.9.1': 'common.dnFields.email',
  'emailAddress': 'common.dnFields.email',
  'E': 'common.dnFields.email',
  'STREET': 'common.dnFields.street',
  'SERIALNUMBER': 'common.dnFields.serial',
}

function FormattedDN({ dn }) {
  const { t } = useTranslation()
  if (!dn) return <span className="text-xs text-text-tertiary">—</span>
  // Parse DN: handles both KEY=value and OID=value formats
  const parts = []
  const regex = /([\w.]+)=([^,]*(?:,(?!\s*[A-Z0-9.]+=).*)*)/g
  let match
  while ((match = regex.exec(dn)) !== null) {
    parts.push({ key: match[1].trim(), value: match[2].trim() })
  }
  if (!parts.length) return <span className="text-xs font-mono text-text-primary break-all">{dn}</span>

  return (
    <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5">
      {parts.map((p, i) => (
        <Fragment key={i}>
          <span className="text-2xs text-text-tertiary whitespace-nowrap py-0.5 text-right">
            {DN_LABEL_KEYS[p.key] ? t(DN_LABEL_KEYS[p.key]) : p.key}
          </span>
          <span className="text-xs font-medium text-text-primary break-all py-0.5">
            {p.value}
          </span>
        </Fragment>
      ))}
    </div>
  )
}

export default function DiscoveredDetailPanel({ item, t }) {
  const [detail, setDetail] = useState(null)
  const [loadingDetail, setLoadingDetail] = useState(false)

  useEffect(() => {
    if (!item?.id || item.status === 'error') return
    let cancelled = false
    setLoadingDetail(true)
    discoveryService.getById(item.id)
      .then(res => { if (!cancelled) setDetail(res.data || res) })
      .catch(() => { if (!cancelled) setDetail(null) })
      .finally(() => { if (!cancelled) setLoadingDetail(false) })
    return () => { cancelled = true }
  }, [item?.id])

  const cert = detail || item
  const isError = item.status === 'error'
  const name = isError ? `${item.target}:${item.port || 443}` : (extractCN(cert.subject) || cert.target || t('common.unknown'))
  const days = item.days_until_expiry
  const isExpired = item.is_expired
  const isExpiring = !isExpired && days != null && days <= 30

  const expiryValue = (() => {
    const dateStr = item.not_after ? formatDate(item.not_after) : '—'
    const suffix = isExpired ? ` (${t('common.expired')})` : isExpiring ? ` (${days}d)` : ''
    return dateStr + suffix
  })()

  // Error troubleshooting hints
  const getErrorHint = (error) => {
    if (!error) return null
    const e = error.toLowerCase()
    if (e.includes('unrecognized_name') || e.includes('sni'))
      return { icon: '🔒', hint: t('discovery.errorHintSni') }
    if (e.includes('connection refused') || e.includes('errno 111'))
      return { icon: '🚫', hint: t('discovery.errorHintRefused') }
    if (e.includes('timed out') || e.includes('errno 110'))
      return { icon: '⏱️', hint: t('discovery.errorHintTimeout') }
    if (e.includes('no route') || e.includes('errno 113') || e.includes('network unreachable'))
      return { icon: '🌐', hint: t('discovery.errorHintNoRoute') }
    if (e.includes('dns') || e.includes('name resolution') || e.includes('getaddrinfo'))
      return { icon: '📡', hint: t('discovery.errorHintDns') }
    if (e.includes('reset') || e.includes('errno 104'))
      return { icon: '⛔', hint: t('discovery.errorHintReset') }
    return null
  }

  if (isError) {
    const errorHint = getErrorHint(item.scan_error)
    return (
      <div className="p-4 space-y-4">
        <CompactSection title={t('common.error')}>
          <div className="space-y-3">
            <CompactGrid>
              <CompactField label={t('discovery.host')} value={`${item.target}:${item.port || 443}`} mono />
              {item.dns_hostname && (
                <CompactField label={t('discovery.dnsHostname')} value={item.dns_hostname} />
              )}
              <CompactField
                label={t('common.status')}
                value={<Badge variant="danger" size="sm" icon={WarningCircle} dot>{t('common.error')}</Badge>}
              />
            </CompactGrid>
            <div className="rounded-lg border border-accent-danger-op20 bg-accent-danger-op5 p-3">
              <div className="text-xs font-mono text-status-danger break-all">{item.scan_error}</div>
            </div>
            {errorHint && (
              <div className="rounded-lg border border-border bg-bg-tertiary p-3 flex items-start gap-2">
                <span className="text-base shrink-0">{errorHint.icon}</span>
                <p className="text-xs text-text-secondary leading-relaxed">{errorHint.hint}</p>
              </div>
            )}
          </div>
        </CompactSection>
        <CompactSection title={t('discovery.scanInfo')}>
          <CompactGrid>
            <CompactField label={t('discovery.firstSeen')} value={item.first_seen ? formatDate(item.first_seen) : '—'} />
            <CompactField label={t('discovery.lastSeen')} value={item.last_seen ? formatDate(item.last_seen) : '—'} />
          </CompactGrid>
        </CompactSection>
      </div>
    )
  }

  return (
    <div className="p-4 space-y-4">
      <CompactSection title={t('discovery.certInfo')}>
        <CompactGrid>
          <CompactField label={t('common.commonName')} value={name} />
          <CompactField label={t('discovery.host')} value={`${item.target}:${item.port || 443}`} />
          {item.sni_hostname && (
            <CompactField label="SNI" value={item.sni_hostname} mono />
          )}
          {item.dns_hostname && (
            <CompactField label={t('discovery.dnsHostname')} value={item.dns_hostname} />
          )}
          <CompactField
            label={t('common.status')}
            value={
              <Badge
                variant={item.status === 'managed' ? 'success' : 'warning'}
                size="sm"
                icon={item.status === 'managed' ? ShieldCheck : Warning}
                dot
              >
                {item.status === 'managed' ? t('discovery.managed') : t('discovery.unmanaged')}
              </Badge>
            }
          />
          <CompactField label={t('common.serialNumber')} value={item.serial_number || '—'} mono />
        </CompactGrid>
      </CompactSection>

      <CompactSection title={t('common.subject')} icon={IdentificationBadge} iconClass="icon-bg-blue">
        <FormattedDN dn={item.subject} />
      </CompactSection>

      <CompactSection title={t('common.issuer')} icon={Stamp} iconClass="icon-bg-violet">
        <FormattedDN dn={item.issuer} />
      </CompactSection>

      {/* Key & Signature Info */}
      {(cert.key_algorithm || cert.signature_algorithm) && (
        <CompactSection title={t('common.keyInformation')}>
          <CompactGrid>
            {cert.key_algorithm && (
              <CompactField label={t('common.keyAlgorithm')} value={`${cert.key_algorithm}${cert.key_size ? ` ${cert.key_size}` : ''}${cert.curve ? ` (${cert.curve})` : ''}`} />
            )}
            {cert.signature_algorithm && (
              <CompactField label={t('common.signatureAlgorithm')} value={cert.signature_algorithm} />
            )}
          </CompactGrid>
        </CompactSection>
      )}

      {/* SANs — use extensions if available, fall back to list data */}
      {cert.extensions?.subject_alt_names?.entries?.length > 0 ? (
        <SubjectAltNames extensions={cert.extensions} />
      ) : (item.san_dns_names?.length > 0 || item.san_ip_addresses?.length > 0) && (
        <CompactSection title={t('discovery.subjectAltNames')}>
          <div className="space-y-2">
            {item.san_dns_names?.length > 0 && (
              <div>
                <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-1">DNS</div>
                <div className="flex flex-wrap gap-1">
                  {item.san_dns_names.map((san, i) => (
                    <Badge key={i} variant="secondary" size="sm">{san}</Badge>
                  ))}
                </div>
              </div>
            )}
            {item.san_ip_addresses?.length > 0 && (
              <div>
                <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-1">IP</div>
                <div className="flex flex-wrap gap-1">
                  {item.san_ip_addresses.map((san, i) => (
                    <Badge key={i} variant="secondary" size="sm">{san}</Badge>
                  ))}
                </div>
              </div>
            )}
          </div>
        </CompactSection>
      )}

      <CompactSection title={t('common.validity')}>
        <CompactGrid>
          <CompactField label={t('common.notBefore')} value={item.not_before ? formatDate(item.not_before) : '—'} />
          <CompactField
            label={t('common.notAfter')}
            value={expiryValue}
            className={isExpired ? 'text-status-danger' : isExpiring ? 'text-status-warning' : ''}
          />
        </CompactGrid>
      </CompactSection>

      <CompactSection title={t('common.fingerprint')}>
        <div className="space-y-2">
          <div>
            <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-0.5">SHA-256</div>
            <div className="text-xs font-mono text-text-primary break-all">{cert.fingerprint_sha256 || item.fingerprint_sha256 || '—'}</div>
          </div>
          {cert.fingerprint_sha1 && (
            <div>
              <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-0.5">SHA-1</div>
              <div className="text-xs font-mono text-text-primary break-all">{cert.fingerprint_sha1}</div>
            </div>
          )}
        </div>
      </CompactSection>

      {/* X.509 Extensions */}
      {cert.extensions && <CertificateExtensions extensions={cert.extensions} defaultOpen={false} />}

      <CompactSection title={t('discovery.scanInfo')}>
        <CompactGrid>
          <CompactField label={t('discovery.firstSeen')} value={item.first_seen ? formatDate(item.first_seen) : '—'} />
          <CompactField label={t('discovery.lastSeen')} value={item.last_seen ? formatDate(item.last_seen) : '—'} />
          {item.last_changed_at && (
            <CompactField label={t('discovery.lastChanged')} value={formatDate(item.last_changed_at)} />
          )}
          {item.scan_error && (
            <CompactField label={t('common.error')} value={item.scan_error} />
          )}
        </CompactGrid>
      </CompactSection>
    </div>
  )
}
