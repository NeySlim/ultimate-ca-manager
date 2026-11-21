import { Certificate, ShieldCheck, Fingerprint } from '@phosphor-icons/react'
import { certificatesService, casService, truststoreService, userCertificatesService } from '../../services'

// Per type: icon, loader and the detail sections its panel offers as tabs
export const INSPECTOR_TYPES = {
  certificate: {
    icon: Certificate, iconClass: 'bg-accent-primary-op15 text-accent-primary',
    fetchById: (id) => certificatesService.getById(id),
    sections: ['overview', 'chain', 'extensions', 'pem'],
  },
  ca: {
    icon: ShieldCheck, iconClass: 'bg-accent-success-op15 text-accent-success',
    fetchById: (id) => casService.getById(id),
    sections: ['overview', 'chain', 'extensions', 'pem'],
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
}
