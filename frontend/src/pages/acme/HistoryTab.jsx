import { useMemo, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Certificate, CheckCircle, XCircle, Clock, ClockCounterClockwise } from '@phosphor-icons/react'
import { Badge, ResponsiveDataTable } from '../../components'
import { cn, daysRemaining, formatDate } from '../../lib/utils'
import CertDetailPanel from './CertDetailPanel'

// The columns the server can sort by; the others are not sortable here
const SERVER_SORT_KEYS = ['common_name', 'valid_to', 'created_at', 'source']

export default function HistoryTab({ history, total, page, perPage, onPageChange, onPerPageChange, search, onSearchChange, onSortChange, caOptions, exportLoader, filterStatus, onFilterStatusChange, filterCA, onFilterCAChange, filterSource, onFilterSourceChange, selectedCert, onSelectCert }) {
  const { t } = useTranslation()

  const handleApplyFilterPreset = useCallback((filters) => {
    if (filters.source) onFilterSourceChange(filters.source)
    else onFilterSourceChange('')
    if (filters.status) onFilterStatusChange(Array.isArray(filters.status) ? filters.status : [filters.status])
    else onFilterStatusChange([])
    if (filters.ca) onFilterCAChange(filters.ca)
    else onFilterCAChange('')
  }, [onFilterStatusChange, onFilterCAChange, onFilterSourceChange])

  const historyColumns = useMemo(() => [
    {
      key: 'common_name',
      header: t('common.commonName'),
      priority: 1,
      sortable: true,
      render: (value, row) => (
        <div className="flex items-center gap-2">
          <div className={cn(
            "w-6 h-6 rounded-lg flex items-center justify-center shrink-0",
            row?.revoked ? "icon-bg-orange" : "icon-bg-blue"
          )}>
            <Certificate size={14} weight="duotone" />
          </div>
          <div className="flex flex-col min-w-0">
            <span className="font-medium truncate">{value}</span>
            {row?.order?.account && (
              <span className="text-xs text-text-tertiary">via {row.order.account}</span>
            )}
          </div>
        </div>
      ),
      mobileRender: (value, row) => (
        <div className="flex items-center justify-between gap-2 w-full">
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <div className={cn(
              "w-6 h-6 rounded-lg flex items-center justify-center shrink-0",
              row?.revoked ? "icon-bg-orange" : "icon-bg-blue"
            )}>
              <Certificate size={14} weight="duotone" />
            </div>
            <span className="font-medium truncate">{value}</span>
          </div>
          <Badge 
            variant={row?.revoked ? 'danger' : 'success'} 
            size="sm"
            icon={row?.revoked ? XCircle : CheckCircle}
          >
            {row?.revoked ? t('common.revoked') : t('common.valid')}
          </Badge>
        </div>
      )
    },
    {
      key: 'status',
      header: t('common.status'),
      priority: 2,
      hideOnMobile: true,
      render: (value, row) => {
        if (row?.revoked) {
          return (
            <Badge variant="danger" size="sm" icon={XCircle} dot>
              {t('common.revoked')}
            </Badge>
          );
        }
        const statusConfig = {
          valid: { variant: 'success', icon: CheckCircle, pulse: true },
          issued: { variant: 'success', icon: CheckCircle, pulse: false },
          pending: { variant: 'warning', icon: Clock, pulse: true },
          processing: { variant: 'info', icon: Clock, pulse: true },
          ready: { variant: 'info', icon: CheckCircle, pulse: false },
          invalid: { variant: 'danger', icon: XCircle, pulse: false },
        };
        const config = statusConfig[value] || statusConfig.valid;
        return (
          <Badge 
            variant={config.variant} 
            size="sm"
            icon={config.icon}
            dot
            pulse={config.pulse}
          >
            {value ? value.charAt(0).toUpperCase() + value.slice(1) : t('common.valid')}
          </Badge>
        );
      }
    },
    {
      key: 'issuer',
      header: t('common.issuer'),
      priority: 3,
      sortable: false,
      hideOnMobile: true,
      render: (value) => (
        <span className="text-sm text-text-secondary">{value || t('common.unknown')}</span>
      ),
      mobileRender: (value) => (
        <div className="flex items-center gap-2 text-xs">
          <span className="text-text-tertiary">CA:</span>
          <span className="text-text-secondary truncate">{value || t('common.unknown')}</span>
        </div>
      )
    },
    {
      key: 'valid_to',
      header: t('common.expires'),
      priority: 4,
      sortable: true,
      render: (value) => {
        if (!value) return <span className="text-text-tertiary">N/A</span>
        const expires = new Date(value)
        const now = new Date()
        const daysLeft = daysRemaining(expires)
        const isExpiring = daysLeft > 0 && daysLeft < 30
        const isExpired = daysLeft <= 0
        return (
          <div className="flex items-center gap-2">
            <Clock size={14} className={cn(
              isExpired ? "text-status-error" : 
              isExpiring ? "text-status-warning" : 
              "text-text-tertiary"
            )} />
            <div className="flex flex-col">
              <span className="text-xs text-text-secondary whitespace-nowrap">{formatDate(value)}</span>
              <span className={cn(
                "text-xs",
                isExpired ? "text-status-error" : 
                isExpiring ? "text-status-warning" : 
                "text-text-tertiary"
              )}>
                {isExpired ? t('common.expired') : t('acme.daysLeft', { count: daysLeft })}
              </span>
            </div>
          </div>
        )
      },
      mobileRender: (value) => {
        if (!value) return null
        const expires = new Date(value)
        const now = new Date()
        const daysLeft = daysRemaining(expires)
        const isExpired = daysLeft <= 0
        return (
          <div className="flex items-center gap-2 text-xs">
            <Clock size={12} className="text-text-tertiary" />
            <span className={isExpired ? "text-status-error" : "text-text-secondary"}>
              {isExpired ? t('common.expired') : `${daysLeft}d`}
            </span>
          </div>
        )
      }
    },
    {
      key: 'source',
      header: t('common.source'),
      sortable: true,
      priority: 3,
      hideOnMobile: true,
      render: (value, row) => {
        const isExternal = value === 'letsencrypt' || value === 'acme_client'
        const label = value === 'letsencrypt'
          ? t('acme.letsEncryptLabel')
          : value === 'acme_client'
            ? (row?.ca_account_label || t('certificates.sourceAcmeClient'))
            : t('acme.localAcmeLabel')
        return (
          <Badge variant={isExternal ? 'green' : 'cyan'} size="sm" dot>
            {label}
          </Badge>
        )
      }
    },
    {
      key: 'challenge_type',
      header: t('acme.method'),
      priority: 4,
      hideOnMobile: true,
      render: (value) => (
        <Badge variant="default" size="sm">
          {value?.toUpperCase() || 'N/A'}
        </Badge>
      )
    },
    {
      key: 'dns_provider',
      header: t('acme.provider'),
      priority: 5,
      hideOnMobile: true,
      render: (value) => (
        <span className="text-sm text-text-secondary">{value || '-'}</span>
      )
    },
    {
      key: 'environment',
      header: t('acme.environment'),
      priority: 5,
      hideOnMobile: true,
      render: (value, row) => {
        if (!value) return <span className="text-text-tertiary">-</span>
        if (value === 'local' || row?.source === 'acme') {
          return (
            <Badge variant="cyan" size="sm">
              {t('acme.localAcmeLabel')}
            </Badge>
          )
        }
        const isProduction = value === 'production'
        return (
          <Badge 
            variant={isProduction ? 'success' : 'warning'} 
            size="sm"
          >
            {isProduction ? t('acme.production') : t('acme.staging')}
          </Badge>
        )
      }
    },
    {
      key: 'created_at',
      header: t('common.issued'),
      priority: 6,
      sortable: true,
      hideOnMobile: true,
      render: (value) => (
        <span className="text-xs text-text-tertiary whitespace-nowrap">
          {value ? formatDate(value) : 'N/A'}
        </span>
      )
    }
  ].map((col) => (SERVER_SORT_KEYS.includes(col.key) ? col : { ...col, sortable: false })), [t])

  return (
    <ResponsiveDataTable
      data={history}
      columns={historyColumns}
      columnStorageKey="acme-history-columns"
      searchable
      searchPlaceholder={t('common.searchCertificates')}
      externalSearch={search}
      onSearchChange={onSearchChange}
      getRowId={(row) => row.id}
      onRowClick={onSelectCert}
      selectedRow={selectedCert}
      sortable
      defaultSort={{ key: 'created_at', direction: 'desc' }}
      onSortChange={onSortChange}
      pagination={{ page, total, perPage, onChange: onPageChange, onPerPageChange }}
      exportEnabled
      exportLoader={exportLoader}
      exportFilename="acme-certificates"
      toolbarFilters={[
        {
          key: 'source',
          value: filterSource,
          onChange: onFilterSourceChange,
          placeholder: t('acme.allSources'),
          options: [
            { value: 'acme', label: t('acme.localAcme') },
            { value: 'acme_client', label: t('certificates.sourceAcmeClient') },
            { value: 'letsencrypt', label: t('acme.letsEncrypt') }
          ]
        },
        {
          key: 'status',
          label: t('common.status'),
          type: 'multiSelect',
          value: filterStatus,
          onChange: onFilterStatusChange,
          placeholder: t('common.allStatus'),
          options: [
            { value: 'valid', label: t('common.valid') },
            { value: 'revoked', label: t('common.revoked') }
          ]
        },
        {
          key: 'ca',
          value: filterCA,
          onChange: onFilterCAChange,
          placeholder: t('acme.allCAs'),
          options: caOptions
        }
      ]}
      filterPresetsKey="ucm-acme-presets"
      densityStorageKey="ucm-acme-density"
      onApplyFilterPreset={handleApplyFilterPreset}
      emptyState={{
        icon: ClockCounterClockwise,
        title: t('acme.noCertificates'),
        description: t('acme.noCertificatesDesc')
      }}
    />
  )
}
