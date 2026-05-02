import { useMemo } from 'react'
import {
  Certificate, X, Info, CheckCircle, Clock, XCircle, LinkBreak
} from '@phosphor-icons/react'
import { Badge, KeyIndicator } from '../../components'
import { formatDate, extractCN, cn } from '../../lib/utils'

export function useCertificateColumns(t) {
  const getStatusBadge = (row) => {
    const isRevoked = row.revoked
    const status = isRevoked ? 'revoked' : row.status || 'unknown'
    const config = {
      valid: { variant: 'success', icon: CheckCircle, label: t('common.valid'), pulse: true },
      expiring: { variant: 'warning', icon: Clock, label: t('common.expiring'), pulse: true },
      expired: { variant: 'danger', icon: XCircle, label: t('common.expired'), pulse: false },
      revoked: { variant: 'danger', icon: X, label: t('common.revoked'), pulse: false },
      unknown: { variant: 'secondary', icon: Info, label: t('common.status'), pulse: false }
    }
    const { variant, icon, label, pulse } = config[status] || config.unknown
    return <Badge variant={variant} size="sm" icon={icon} dot pulse={pulse}>{label}</Badge>
  }

  const columns = useMemo(() => [
    {
      key: 'cn',
      header: t('common.commonName'),
      priority: 1,
      sortable: true,
      render: (val, row) => (
        <div className="flex items-center gap-2">
          <div className={cn(
            "w-6 h-6 rounded-lg flex items-center justify-center shrink-0",
            row.has_private_key ? "icon-bg-emerald" : "icon-bg-blue"
          )}>
            <Certificate size={14} weight="duotone" />
          </div>
          <span className="font-medium truncate">{val}</span>
          <KeyIndicator hasKey={row.has_private_key} size={14} />
          {row.isOrphan && <Badge variant="warning" size="sm" icon={LinkBreak} title={t('certificates.orphanDescription')}>{t('certificates.orphan')}</Badge>}
          {row.source === 'import' && <Badge variant="secondary" size="sm" dot>IMPORT</Badge>}
          {row.source === 'acme' && <Badge variant="cyan" size="sm" dot>LOCAL ACME</Badge>}
          {row.source === 'letsencrypt' && <Badge variant="green" size="sm" dot>LET'S ENCRYPT</Badge>}
          {row.source === 'scep' && <Badge variant="orange" size="sm" dot>SCEP</Badge>}
          {row.source === 'msca' && <Badge variant="purple" size="sm" dot>ADCS</Badge>}
          {row.source === 'est' && <Badge variant="yellow" size="sm" dot>EST</Badge>}
        </div>
      ),
      // Mobile: Icon + CN left + status badge right
      mobileRender: (val, row) => (
        <div className="flex items-center justify-between gap-2 w-full">
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <div className={cn(
              "w-6 h-6 rounded-lg flex items-center justify-center shrink-0",
              row.has_private_key ? "icon-bg-emerald" : "icon-bg-blue"
            )}>
              <Certificate size={14} weight="duotone" />
            </div>
            <span className="font-medium truncate">{val || row.cn || row.common_name || t('common.certificate')}</span>
            <KeyIndicator hasKey={row.has_private_key} size={12} />
          </div>
          <div className="shrink-0">
            {getStatusBadge(row)}
          </div>
        </div>
      )
    },
    {
      key: 'status',
      header: t('common.status'),
      priority: 2,
      sortable: true, // Groups by status type, then alphabetically
      hideOnMobile: true, // Status shown in CN mobileRender
      render: (val, row) => {
        const isRevoked = row.revoked
        const status = isRevoked ? 'revoked' : val || 'unknown'
        const config = {
          valid: { variant: 'success', icon: CheckCircle, label: t('common.valid'), pulse: true },
          expiring: { variant: 'warning', icon: Clock, label: t('common.expiring'), pulse: true },
          expired: { variant: 'danger', icon: XCircle, label: t('common.expired'), pulse: false },
          revoked: { variant: 'danger', icon: X, label: t('common.revoked'), pulse: false },
          unknown: { variant: 'secondary', icon: Info, label: t('common.status'), pulse: false }
        }
        const { variant, icon, label, pulse } = config[status] || config.unknown
        return (
          <Badge variant={variant} size="sm" icon={icon} dot pulse={pulse}>
            {label}
          </Badge>
        )
      }
    },
    {
      key: 'compliance_grade',
      header: t('compliance.grade'),
      priority: 2,
      sortable: true,
      hideOnMobile: true,
      render: (val, row) => {
        const grade = row.compliance_grade || 'F'
        const score = row.compliance_score ?? 0
        const config = {
          'A+': { variant: 'emerald', label: 'A+' },
          'A': { variant: 'success', label: 'A' },
          'B': { variant: 'blue', label: 'B' },
          'C': { variant: 'warning', label: 'C' },
          'D': { variant: 'orange', label: 'D' },
          'F': { variant: 'danger', label: 'F' },
        }
        const { variant, label } = config[grade] || config['F']
        return (
          <Badge variant={variant} size="sm" title={`${score}/100`}>
            {label}
          </Badge>
        )
      }
    },
    {
      key: 'issuer',
      header: t('common.issuer'),
      priority: 3,
      sortable: true,
      render: (val, row) => (
        <span className="text-text-secondary truncate">
          {extractCN(val) || row.issuer_name || '—'}
        </span>
      ),
      // Mobile: labeled CA info
      mobileRender: (val, row) => (
        <div className="flex items-center gap-2 text-xs">
          <span className="text-text-tertiary">CA:</span>
          <span className="text-text-secondary truncate">{extractCN(val) || row.issuer_name || '—'}</span>
        </div>
      )
    },
    {
      key: 'valid_to',
      header: t('common.expires'),
      priority: 4,
      sortable: true,
      mono: true,
      render: (val) => (
        <span className="text-xs text-text-secondary whitespace-nowrap">
          {formatDate(val)}
        </span>
      ),
      // Mobile: labeled expiration with badges
      mobileRender: (val, row) => (
        <div className="flex items-center gap-2 flex-wrap">
          <div className="flex items-center gap-2 text-xs">
            <span className="text-text-tertiary">{t('common.expires').substring(0, 3)}:</span>
            <span className="text-text-secondary font-mono">{formatDate(val)}</span>
          </div>
          {row.isOrphan && <Badge variant="warning" size="xs" icon={LinkBreak}>{t('certificates.orphan')}</Badge>}
          {row.source === 'import' && <Badge variant="secondary" size="xs" dot>IMPORT</Badge>}
          {row.source === 'acme' && <Badge variant="cyan" size="xs" dot>LOCAL ACME</Badge>}
          {row.source === 'letsencrypt' && <Badge variant="green" size="xs" dot>LET'S ENCRYPT</Badge>}
          {row.source === 'scep' && <Badge variant="orange" size="xs" dot>SCEP</Badge>}
          {row.source === 'msca' && <Badge variant="purple" size="xs" dot>ADCS</Badge>}
          {row.source === 'est' && <Badge variant="yellow" size="xs" dot>EST</Badge>}
        </div>
      )
    },
    {
      key: 'key_type',
      header: t('common.keyType'),
      hideOnMobile: true,
      sortable: true,
      mono: true,
      render: (val, row) => (
        <span className="text-xs text-text-secondary">
          {row.key_algorithm || row.key_algo || val || 'RSA'}
        </span>
      )
    }
  ], [t])

  return columns
}
