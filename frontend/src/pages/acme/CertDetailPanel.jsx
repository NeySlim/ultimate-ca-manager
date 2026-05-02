import { useTranslation } from 'react-i18next'
import { ClockCounterClockwise, Key, Globe, CheckCircle } from '@phosphor-icons/react'
import { Badge, CompactSection, CompactGrid, CompactField, CompactStats, CompactHeader } from '../../components'
import { formatDate } from '../../lib/utils'

export default function CertDetailPanel({ cert }) {
  const { t } = useTranslation()

  return (
    <div className="p-3 space-y-3">
      <CompactHeader
        icon={ClockCounterClockwise}
        iconClass={cert.revoked ? "bg-status-error-op20" : "bg-status-success-op20"}
        title={cert.common_name}
        subtitle={`${t('common.issuer')}: ${cert.issuer || t('acme.unknownCA')}`}
        badge={
          <Badge variant={cert.revoked ? 'danger' : 'success'} size="sm">
            {!cert.revoked && <CheckCircle size={10} weight="fill" />}
            {cert.revoked ? t('common.revoked') : t('common.valid')}
          </Badge>
        }
      />

      <CompactStats stats={[
        { icon: Key, value: cert.order?.account || t('common.unknown') },
        { icon: Globe, value: cert.order?.status || t('common.na') },
      ]} />
      
      <CompactSection title={t('common.certificateDetails')}>
        <CompactGrid>
          <CompactField autoIcon="commonName" label={t('common.commonName')} value={cert.common_name} copyable />
          <CompactField autoIcon="serialNumber" label={t('common.serialNumber')} value={cert.serial} mono copyable />
          <CompactField autoIcon="issuer" label={t('common.issuer')} value={cert.issuer || t('common.unknown')} />
        </CompactGrid>
      </CompactSection>
      
      <CompactSection title={t('common.validity')}>
        <CompactGrid>
          <CompactField autoIcon="validFrom" label={t('common.validFrom')} value={cert.valid_from ? formatDate(cert.valid_from) : t('common.na')} />
          <CompactField autoIcon="validTo" label={t('common.validTo')} value={cert.valid_to ? formatDate(cert.valid_to) : t('common.na')} />
          <CompactField autoIcon="issued" label={t('common.issued')} value={cert.created_at ? formatDate(cert.created_at) : t('common.na')} />
        </CompactGrid>
      </CompactSection>
      
      {cert.order && (
        <CompactSection title={t('acme.acmeOrder')}>
          <CompactGrid>
            <CompactField autoIcon="account" label={t('acme.account')} value={cert.order.account} />
            <CompactField autoIcon="orderStatus" label={t('acme.orderStatus')} value={cert.order.status} />
            <CompactField autoIcon="orderId" label={t('acme.orderId')} value={cert.order.order_id} mono copyable />
          </CompactGrid>
        </CompactSection>
      )}
    </div>
  )
}
