/**
 * FloatingDetailWindow — Renders entity detail in a floating window
 * 
 * Wraps FloatingWindow + entity-specific content (CertificateDetails, CA details, etc.)
 * Fetches full entity data on mount, shows loading state.
 */
import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Certificate, ShieldCheck, Fingerprint } from '@phosphor-icons/react'
import { FloatingWindow } from './ui/FloatingWindow'
import { CertificateDetails } from './CertificateDetails'
import { CompactSection, CompactGrid, CompactField } from './DetailCard'
import { Badge } from './Badge'
import { certificatesService, casService, truststoreService } from '../services'
import { useWindowManager } from '../contexts/WindowManagerContext'
import { extractData, formatDate } from '../lib/utils'
import { LoadingSpinner } from './LoadingSpinner'

const ENTITY_CONFIG = {
  certificate: {
    icon: Certificate,
    iconClass: 'bg-accent-primary/15 text-accent-primary',
    service: () => certificatesService,
    fetchById: (id) => certificatesService.getById(id),
    getTitle: (data) => data?.common_name || data?.subject || `Certificate #${data?.id}`,
    getSubtitle: (data) => data?.issuer_cn || '',
  },
  ca: {
    icon: ShieldCheck,
    iconClass: 'bg-accent-success/15 text-accent-success',
    service: () => casService,
    fetchById: (id) => casService.getById(id),
    getTitle: (data) => data?.common_name || data?.descr || `CA #${data?.id}`,
    getSubtitle: (data) => data?.is_root ? 'Root CA' : 'Intermediate',
  },
  truststore: {
    icon: Fingerprint,
    iconClass: 'bg-accent-warning/15 text-accent-warning',
    service: () => truststoreService,
    fetchById: (id) => truststoreService.getById(id),
    getTitle: (data) => data?.name || data?.subject || `Trust Store #${data?.id}`,
    getSubtitle: (data) => data?.purpose || '',
  },
}

export function FloatingDetailWindow({ windowInfo }) {
  const { t } = useTranslation()
  const { closeWindow, focusWindow } = useWindowManager()
  const [data, setData] = useState(windowInfo.data?.fullData || null)
  const [loading, setLoading] = useState(!windowInfo.data?.fullData)
  const [minimized, setMinimized] = useState(false)

  const config = ENTITY_CONFIG[windowInfo.type]
  if (!config) return null

  useEffect(() => {
    if (data) return
    let cancelled = false

    const fetchData = async () => {
      try {
        setLoading(true)
        const res = await config.fetchById(windowInfo.entityId)
        if (!cancelled) {
          setData(extractData(res) || res.data || res)
        }
      } catch (err) {
        console.error(`Failed to load ${windowInfo.type} ${windowInfo.entityId}:`, err)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    fetchData()
    return () => { cancelled = true }
  }, [windowInfo.entityId, windowInfo.type])

  const title = data ? config.getTitle(data) : `Loading...`
  const subtitle = data ? config.getSubtitle(data) : ''

  return (
    <FloatingWindow
      storageKey={`ucm-detail-${windowInfo.id}`}
      defaultPos={windowInfo.defaultPos}
      constraints={{ minW: 380, maxW: 900, minH: 300, defW: 520, defH: 500 }}
      minimized={minimized}
      onMinimizeToggle={() => setMinimized(!minimized)}
      onClose={() => closeWindow(windowInfo.id)}
      onFocus={() => focusWindow(windowInfo.id)}
      zIndex={windowInfo.zIndex}
      title={title}
      subtitle={subtitle}
      icon={config.icon}
      iconClass={config.iconClass}
      key={windowInfo._tileKey || windowInfo.id}
    >
      {loading ? (
        <div className="flex-1 flex items-center justify-center">
          <LoadingSpinner size="md" />
        </div>
      ) : data ? (
        <div className="flex-1 overflow-y-auto p-0">
          <DetailContent type={windowInfo.type} data={data} />
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center text-text-tertiary text-sm">
          {t('common.notFound', 'Not found')}
        </div>
      )}
    </FloatingWindow>
  )
}

/**
 * DetailContent — Renders the appropriate detail view based on entity type
 */
function DetailContent({ type, data }) {
  if (type === 'certificate') {
    return (
      <CertificateDetails
        certificate={data}
        compact={false}
        showActions={false}
        showPem={true}
      />
    )
  }

  if (type === 'ca') {
    return <CADetailContent data={data} />
  }

  if (type === 'truststore') {
    return <TrustStoreDetailContent data={data} />
  }

  return null
}

function CADetailContent({ data }) {
  const { t } = useTranslation()
  const ca = data

  return (
    <div className="space-y-0">
      <CompactSection title={t('common.generalInfo', 'General')} icon={ShieldCheck} iconClass="icon-bg-emerald">
        <CompactGrid>
          <CompactField label={t('common.commonName', 'Common Name')} value={ca.common_name || ca.descr} />
          <CompactField label={t('common.type', 'Type')} value={
            <Badge variant={ca.is_root ? 'amber' : 'blue'} size="sm" dot>
              {ca.is_root ? t('common.rootCA', 'Root CA') : t('common.intermediate', 'Intermediate')}
            </Badge>
          } />
          {ca.key_type && <CompactField label={t('common.keyType', 'Key Type')} value={`${ca.key_type} ${ca.key_length || ''}`} />}
          {ca.serial && <CompactField label={t('common.serial', 'Serial')} value={ca.serial} mono />}
        </CompactGrid>
      </CompactSection>

      <CompactSection title={t('common.subject', 'Subject')} icon={Certificate} iconClass="icon-bg-blue">
        <CompactGrid>
          {ca.dn_commonname && <CompactField label="CN" value={ca.dn_commonname} />}
          {ca.dn_organization && <CompactField label="O" value={ca.dn_organization} />}
          {ca.dn_organizationalunit && <CompactField label="OU" value={ca.dn_organizationalunit} />}
          {ca.dn_country && <CompactField label="C" value={ca.dn_country} />}
          {ca.dn_state && <CompactField label="ST" value={ca.dn_state} />}
          {ca.dn_city && <CompactField label="L" value={ca.dn_city} />}
          {ca.dn_email && <CompactField label="Email" value={ca.dn_email} />}
        </CompactGrid>
      </CompactSection>

      {(ca.valid_from || ca.valid_to) && (
        <CompactSection title={t('common.validity', 'Validity')} icon={Certificate} iconClass="icon-bg-teal">
          <CompactGrid>
            {ca.valid_from && <CompactField label={t('common.validFrom', 'Valid From')} value={formatDate(ca.valid_from)} />}
            {ca.valid_to && <CompactField label={t('common.validTo', 'Valid To')} value={formatDate(ca.valid_to)} />}
          </CompactGrid>
        </CompactSection>
      )}
    </div>
  )
}

function TrustStoreDetailContent({ data }) {
  const { t } = useTranslation()
  const cert = data

  return (
    <div className="space-y-0">
      <CompactSection title={t('common.generalInfo', 'General')} icon={Fingerprint} iconClass="icon-bg-amber">
        <CompactGrid>
          <CompactField label={t('common.name', 'Name')} value={cert.name} />
          <CompactField label={t('trustStore.purpose', 'Purpose')} value={
            <Badge variant="secondary" size="sm">{cert.purpose}</Badge>
          } />
          {cert.added_by && <CompactField label={t('trustStore.addedBy', 'Added By')} value={cert.added_by} />}
        </CompactGrid>
      </CompactSection>

      <CompactSection title={t('common.subject', 'Subject')} icon={Certificate} iconClass="icon-bg-blue">
        <CompactGrid>
          <CompactField label={t('common.subject', 'Subject')} value={cert.subject} />
          <CompactField label={t('common.issuer', 'Issuer')} value={cert.issuer} />
          {cert.serial_number && <CompactField label={t('common.serial', 'Serial')} value={cert.serial_number} mono />}
        </CompactGrid>
      </CompactSection>

      {(cert.not_before || cert.not_after) && (
        <CompactSection title={t('common.validity', 'Validity')} icon={Certificate} iconClass="icon-bg-teal">
          <CompactGrid>
            {cert.not_before && <CompactField label={t('common.validFrom', 'Valid From')} value={formatDate(cert.not_before)} />}
            {cert.not_after && <CompactField label={t('common.validTo', 'Valid To')} value={formatDate(cert.not_after)} />}
          </CompactGrid>
        </CompactSection>
      )}

      {(cert.fingerprint_sha256 || cert.fingerprint_sha1) && (
        <CompactSection title={t('common.fingerprints', 'Fingerprints')} icon={Fingerprint} iconClass="icon-bg-violet">
          <CompactGrid cols={1}>
            {cert.fingerprint_sha256 && <CompactField label="SHA-256" value={cert.fingerprint_sha256} mono />}
            {cert.fingerprint_sha1 && <CompactField label="SHA-1" value={cert.fingerprint_sha1} mono />}
          </CompactGrid>
        </CompactSection>
      )}

      {cert.notes && (
        <CompactSection title={t('common.notes', 'Notes')} icon={Certificate} iconClass="icon-bg-teal">
          <p className="text-xs text-text-secondary whitespace-pre-wrap">{cert.notes}</p>
        </CompactSection>
      )}
    </div>
  )
}
