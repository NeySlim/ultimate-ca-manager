/**
 * Per-type facts shared by the detail window and the entity actions hook:
 * the service behind each type, the RBAC resource it is judged by, and the
 * title/subtitle of its window.
 */
import { certificatesService, casService, truststoreService, userCertificatesService } from '../services'
import { extractCN } from './utils'

// The RBAC resource each type is judged by, matching the scope its route
// enforces: a type missing here would be guarded as a certificate.
export const ENTITY_RESOURCE = {
  certificate: 'certificates',
  ca: 'cas',
  truststore: 'truststore',
  user_certificate: 'user_certificates',
}

const SERVICES = {
  certificate: () => certificatesService,
  ca: () => casService,
  truststore: () => truststoreService,
  user_certificate: () => userCertificatesService,
}

export const entityService = (type) => SERVICES[type]?.()

export function entityTitle(type, data, t) {
  switch (type) {
    case 'certificate':
      return data?.common_name || data?.subject || t('details.entityTitle.certificate', { id: data?.id })
    case 'ca':
      return data?.common_name || data?.descr || t('details.entityTitle.ca', { id: data?.id })
    case 'truststore':
      return data?.name || data?.subject || t('details.entityTitle.truststore', { id: data?.id })
    case 'user_certificate':
      return data?.name || data?.cert_subject || t('details.entityTitle.userCertificate', { id: data?.id })
    default:
      return ''
  }
}

export function entitySubtitle(type, data, t) {
  switch (type) {
    case 'certificate': return data?.issuer ? extractCN(data.issuer) : ''
    case 'ca': return data?.is_root ? t('common.rootCA') : t('common.intermediate')
    case 'truststore': return data?.purpose || ''
    case 'user_certificate': return data?.owner ? t('details.ownerLabel', { owner: data.owner }) : ''
    default: return ''
  }
}
