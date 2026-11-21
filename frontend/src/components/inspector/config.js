import { Certificate, Fingerprint, CheckCircle, Vault, ChartBar } from '@phosphor-icons/react'
import { certificatesService, truststoreService, userCertificatesService, approvalsService, keyRecoveryService } from '../../services'
import { requestTitle } from '../../pages/approvals/approvalModel'
import { fetchReport, reportName } from '../../pages/reports/reportModel'

// Per type: icon, loader and the detail sections its panel offers as tabs
export const INSPECTOR_TYPES = {
  certificate: {
    icon: Certificate, iconClass: 'bg-accent-primary-op15 text-accent-primary',
    fetchById: (id) => certificatesService.getById(id),
    // The PEM of the 3.0 stays, after the four sections of the Atelier detail
    sections: ['overview', 'chain', 'extensions', 'history', 'pem'],
  },
  truststore: {
    icon: Fingerprint, iconClass: 'bg-accent-warning-op15 text-accent-warning',
    fetchById: (id) => truststoreService.getById(id),
    sections: ['overview', 'chain', 'pem'],
  },
  user_certificate: {
    icon: Certificate, iconClass: 'bg-accent-primary-op15 text-accent-primary',
    fetchById: (id) => userCertificatesService.getById(id),
    sections: ['overview', 'chain', 'extensions', 'pem'],
  },
  // Work queue objects: their panel comes from queueDetails.js, their title from `title`
  approval: {
    icon: CheckCircle,
    fetchById: (id) => approvalsService.getById(id),
    sections: ['request', 'log'],
    title: (data, t) => requestTitle(data, t),
  },
  key_recovery: {
    icon: Vault,
    fetchById: (id) => keyRecoveryService.get(id),
    sections: ['request', 'log'],
    title: (data) => data?.cert_cn || data?.cert_refid || `#${data?.id}`,
  },
  report: {
    icon: ChartBar,
    fetchById: (key) => fetchReport(key),
    sections: ['report', 'runs', 'preview'],
    title: (data, t) => reportName(data?.key, t),
  },
}
