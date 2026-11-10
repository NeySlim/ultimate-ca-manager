/**
 * CSRPanel: pure presentation of a pending CSR or of the certificate a CSR
 * produced (`variant="signed"`, the history tab). Action rows stay with the
 * caller and arrive as children; `section` picks one named part (./sections.js).
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { FileText, Key, Clock, Certificate, CheckCircle, Stamp, Copy } from '@phosphor-icons/react'
import { Badge } from '../Badge'
import { CompactSection, CompactGrid, CompactField, CompactHeader, CompactStats } from '../DetailCard'
import { PostQuantumBadge } from '../PostQuantumBadge'
import { daysSinceExpiry, expiryVariant, hasExpiry } from '../../lib/expiry'
import { keyAlgorithmLabel } from '../../lib/keyAlgorithms'
import { cn, formatDate } from '../../lib/utils'
import { useClipboard } from '../../hooks/useClipboard'
import { Button } from '../Button'
import { showSection } from './sections'

export function CSRPanel({ csr, variant = 'pending', section = 'all', showPem = true, children }) {
  const { t } = useTranslation()
  if (!csr) return null
  const on = (...names) => showSection(section, ...names)
  return variant === 'signed'
    ? <SignedBody cert={csr} t={t} on={on}>{children}</SignedBody>
    : <PendingBody csr={csr} t={t} on={on} showPem={showPem}>{children}</PendingBody>
}

function PendingBody({ csr, t, on, showPem, children }) {
  const [showFullPem, setShowFullPem] = useState(false)
  const { copy: copyPem, isCopied } = useClipboard()
  const pemCopied = isCopied('pem')
  const sans = csr.sans || csr.san_dns
  return (
    <div className="p-3 space-y-3">
      {on('overview') && (<>
      <CompactHeader
        icon={FileText}
        iconClass="bg-accent-warning-op20"
        title={csr.common_name || csr.cn || t('csrs.unnamedCSR')}
        subtitle={csr.organization}
        badge={
          <div className="flex gap-1">
            <Badge variant="warning" size="sm" icon={Clock}>{t('common.pending')}</Badge>
            {csr.has_private_key && <Badge variant="success" size="sm" icon={Key}>{t('common.hasKey')}</Badge>}
            <PostQuantumBadge postQuantum={csr.post_quantum} algorithm={csr.key_algorithm} />
          </div>
        }
      />

      <CompactStats stats={[
        { icon: Clock, value: csr.created_at ? formatDate(csr.created_at, 'short') : '—' },
        { icon: Key, value: [keyAlgorithmLabel(csr.key_algorithm, t, csr.security_level) || '—', csr.key_size].filter(Boolean).join(' ') },
      ]} />

      {/* Caller content (its action row) sits under the summary */}
      {children}

      <CompactSection title={t('common.subject')}>
        <CompactGrid>
          <CompactField autoIcon="commonName" label={t('common.commonName')} value={csr.common_name || csr.cn} className="col-span-2" />
          <CompactField autoIcon="organization" label={t('common.organization')} value={csr.organization} />
          <CompactField autoIcon="orgUnit" label={t('common.orgUnit')} value={csr.organizational_unit} />
          <CompactField autoIcon="country" label={t('common.country')} value={csr.country} />
          <CompactField autoIcon="state" label={t('common.state')} value={csr.state} />
          <CompactField autoIcon="locality" label={t('common.locality')} value={csr.locality} />
          <CompactField autoIcon="email" label={t('common.email')} value={csr.email} />
        </CompactGrid>
      </CompactSection>

      <CompactSection title={t('common.keyInformation')}>
        <CompactGrid>
          <CompactField autoIcon="algorithm" label={t('common.algorithm')} value={keyAlgorithmLabel(csr.key_algorithm, t, csr.security_level) || '—'} />
          <CompactField autoIcon="keySize" label={t('common.keySize')} value={csr.key_size} />
          <CompactField autoIcon="signature" label={t('common.signature')} value={csr.signature_algorithm} />
        </CompactGrid>
      </CompactSection>

      {(csr.sans?.length > 0 || csr.san_dns?.length > 0) && (
        <CompactSection title={t('common.subjectAltNames')}>
          <div className="text-xs text-text-secondary space-y-1">
            {(sans || []).map((san, i) => (
              <div key={i} className="font-mono bg-bg-tertiary px-2 py-1 rounded">
                {san}
              </div>
            ))}
          </div>
        </CompactSection>
      )}

      <CompactSection title={t('common.timeline')}>
        <CompactGrid>
          <CompactField autoIcon="created" label={t('common.created')} value={csr.created_at ? formatDate(csr.created_at) : '—'} />
          <CompactField autoIcon="requester" label={t('csrs.requester')} value={csr.requester || csr.created_by} />
        </CompactGrid>
      </CompactSection>
      </>)}

      {on('pem') && showPem && csr.pem && (
        <CompactSection title={t('details.csrPem')} collapsible defaultOpen={false}>
          <div className="relative">
            <pre className={cn(
              "text-2xs font-mono text-text-secondary bg-tertiary-op50 p-2 rounded overflow-x-auto",
              !showFullPem && "max-h-24 overflow-hidden"
            )}>
              {csr.pem}
            </pre>
          </div>
          <div className="flex gap-2 mt-2">
            <Button type="button" size="sm" variant="ghost"
              onClick={(e) => { e.stopPropagation(); setShowFullPem(!showFullPem) }}>
              {showFullPem ? t('details.showLess') : t('details.showFull')}
            </Button>
            <Button type="button" size="sm" variant="ghost"
              onClick={(e) => { e.stopPropagation(); copyPem(csr.pem, 'pem') }}>
              {pemCopied ? <CheckCircle size={14} /> : <Copy size={14} />}
              {pemCopied ? t('common.copied') : t('details.copyPem')}
            </Button>
          </div>
        </CompactSection>
      )}
    </div>
  )
}

function SignedBody({ cert, t, on, children }) {
  // `|| 0` would turn a null expiry date into "0 days left" and the old -1
  // "no expiry" sentinel into "Expired".
  const daysRemaining = cert.days_remaining
  const expiryBadge = expiryVariant(daysRemaining)
  const isAcme = cert.source === 'acme'
  const isScep = cert.source === 'scep'
  if (!on('overview')) return null
  return (
    <div className="p-3 space-y-3">
      <CompactHeader
        icon={Certificate}
        iconClass="bg-accent-success-op20"
        title={cert.common_name || cert.cn || t('csrs.unnamedCertificate')}
        subtitle={cert.organization}
        badge={
          <div className="flex gap-1">
            <Badge variant="success" size="sm" icon={CheckCircle}>{t('csrs.signed')}</Badge>
            {isAcme && <Badge variant="info" size="sm">ACME</Badge>}
            {isScep && <Badge variant="purple" size="sm">SCEP</Badge>}
          </div>
        }
      />

      <CompactStats stats={[
        { icon: Stamp, value: cert.signed_by || cert.issuer_name || '—' },
        { icon: Clock, value: hasExpiry(daysRemaining)
            ? t('csrs.remaining', { days: daysRemaining })
            : t('common.never') },
      ]} />

      {children}

      <CompactSection title={t('common.signingDetails')}>
        <CompactGrid>
          <CompactField autoIcon="signedBy" label={t('common.signedBy')} value={cert.signed_by || cert.issuer_name} className="col-span-2" />
          <CompactField autoIcon="signedAt" label={t('csrs.signed')} value={cert.signed_at ? formatDate(cert.signed_at) : formatDate(cert.valid_from)} />
          <CompactField autoIcon="expires" label={t('common.expires')} value={cert.valid_to ? formatDate(cert.valid_to) : '—'} />
          <CompactField
            autoIcon="status" label={t('common.status')}
            value={
              <Badge variant={expiryBadge} size="sm">
                {!hasExpiry(daysRemaining)
                  ? t('common.never')
                  : daysRemaining <= 0
                    ? t('details.expiredDaysAgo', { count: daysSinceExpiry(daysRemaining) })
                    : t('csrs.daysLeft', { days: daysRemaining })}
              </Badge>
            }
          />
        </CompactGrid>
      </CompactSection>

      <CompactSection title={t('common.subject')}>
        <CompactGrid>
          <CompactField autoIcon="commonName" label={t('common.commonName')} value={cert.common_name || cert.cn} className="col-span-2" />
          <CompactField autoIcon="organization" label={t('common.organization')} value={cert.organization} />
          <CompactField autoIcon="orgUnit" label={t('common.orgUnit')} value={cert.organizational_unit} />
          <CompactField autoIcon="country" label={t('common.country')} value={cert.country} />
          <CompactField autoIcon="state" label={t('common.state')} value={cert.state} />
        </CompactGrid>
      </CompactSection>

      <CompactSection title={t('common.keyInformation')}>
        <CompactGrid>
          <CompactField autoIcon="algorithm" label={t('common.algorithm')} value={keyAlgorithmLabel(cert.key_algorithm, t, cert.security_level) || '—'} />
          <CompactField autoIcon="keySize" label={t('common.keySize')} value={cert.key_size} />
          <CompactField autoIcon="serial" label={t('common.serial')} value={cert.serial_number} copyable mono className="col-span-2" />
        </CompactGrid>
      </CompactSection>

      <CompactSection title={t('common.timeline')}>
        <CompactGrid>
          <CompactField autoIcon="created" label={t('csrs.csrCreated')} value={cert.created_at ? formatDate(cert.created_at) : '—'} />
          <CompactField autoIcon="issued" label={t('csrs.certificateIssued')} value={cert.valid_from ? formatDate(cert.valid_from) : '—'} />
        </CompactGrid>
      </CompactSection>
    </div>
  )
}
