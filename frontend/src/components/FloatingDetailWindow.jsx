/**
 * FloatingDetailWindow — Renders entity detail in a floating window
 * 
 * Wraps FloatingWindow + entity-specific content (CertificateDetails, CA details, etc.)
 * Fetches full entity data on mount, shows loading state.
 */
import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Certificate, ShieldCheck, Fingerprint, Trash, X, ArrowsClockwise } from '@phosphor-icons/react'
import { FloatingWindow } from './ui/FloatingWindow'
import { CertificateDetails } from './CertificateDetails'
import { CADetails } from './CADetails'
import { TrustCertDetails } from './TrustCertDetails'
import { certificatesService, casService, truststoreService } from '../services'
import { useWindowManager } from '../contexts/WindowManagerContext'
import { useNotification } from '../contexts'
import { extractData } from '../lib/utils'
import { LoadingSpinner } from './LoadingSpinner'
import { ExportActions } from './ExportActions'
import { cn } from '../lib/utils'

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
    getSubtitle: (data) => data?.is_root ? 'common.rootCA' : 'common.intermediate',
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
  const { closeWindow, focusWindow, sameWindow } = useWindowManager()
  const { showSuccess, showError } = useNotification()
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
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    fetchData()
    return () => { cancelled = true }
  }, [windowInfo.entityId, windowInfo.type])

  // Header action handlers
  const handleExport = async (format = 'pem', options = {}) => {
    try {
      const service = config.service()
      const id = windowInfo.entityId
      const name = data?.cn || data?.common_name || data?.name || windowInfo.type
      
      const res = await service.export(id, format, options)
      const blob = res instanceof Blob ? res : new Blob([res.data || res], { type: 'application/octet-stream' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const ext = { pkcs12: 'p12', pkcs7: 'p7b' }[format] || format
      a.download = `${name}.${ext}`
      a.click()
      URL.revokeObjectURL(url)
      showSuccess(t('common.exported'))
    } catch (err) {
      showError(t('common.exportFailed'))
    }
  }

  const handleRevoke = async () => {
    if (!confirm(t('certificates.confirmRevoke', 'Revoke this certificate?'))) return
    try {
      await certificatesService.revoke(windowInfo.entityId)
      showSuccess(t('certificates.revoked', 'Certificate revoked'))
      closeWindow(windowInfo.id)
    } catch (err) {
      showError(t('certificates.revokeFailed', 'Revoke failed'))
    }
  }

  const handleRenew = async () => {
    try {
      await certificatesService.renew(windowInfo.entityId)
      showSuccess(t('certificates.renewed', 'Certificate renewed'))
      closeWindow(windowInfo.id)
    } catch (err) {
      showError(t('certificates.renewFailed', 'Renew failed'))
    }
  }

  const handleDelete = async () => {
    if (!confirm(t('common.confirmDelete'))) return
    try {
      const service = config.service()
      await service.delete(windowInfo.entityId)
      showSuccess(t('common.deleted'))
      closeWindow(windowInfo.id)
    } catch (err) {
      showError(t('common.deleteFailed'))
    }
  }

  const title = data ? config.getTitle(data) : t('common.loading')
  const subtitle = data ? (windowInfo.type === 'ca' ? t(config.getSubtitle(data)) : config.getSubtitle(data)) : ''

  // Build action bar props
  const isCert = windowInfo.type === 'certificate'
  const hasPrivateKey = isCert ? !!data?.has_private_key : !!data?.has_private_key
  const actionBarProps = data ? {
    onExport: handleExport,
    hasPrivateKey,
    onRenew: isCert && !data.revoked && data.has_private_key ? handleRenew : null,
    onRevoke: isCert && !data.revoked ? handleRevoke : null,
    onDelete: handleDelete,
    t,
  } : null

  return (
    <FloatingWindow
      storageKey={sameWindow ? 'ucm-detail-single' : `ucm-detail-${windowInfo.id}`}
      defaultPos={windowInfo.defaultPos}
      forcePosition={!!windowInfo._tileKey}
      constraints={{ minW: 420, maxW: 800, minH: 300, defW: 500, defH: 460 }}
      minimized={minimized}
      onMinimizeToggle={() => setMinimized(!minimized)}
      onClose={() => closeWindow(windowInfo.id)}
      onFocus={() => focusWindow(windowInfo.id)}
      zIndex={windowInfo.zIndex}
      title={title}
      subtitle={subtitle}
      icon={config.icon}
      iconClass={config.iconClass}
    >
      {loading ? (
        <div className="flex-1 flex items-center justify-center">
          <LoadingSpinner size="md" />
        </div>
      ) : data ? (
        <>
          <ActionBar {...actionBarProps} />
          <div className="flex-1 overflow-y-auto p-0">
            <DetailContent type={windowInfo.type} data={data} />
          </div>
        </>
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
        embedded={true}
      />
    )
  }

  if (type === 'ca') {
    return (
      <CADetails
        ca={data}
        showActions={false}
        showPem={true}
        embedded={true}
      />
    )
  }

  if (type === 'truststore') {
    return (
      <TrustCertDetails
        cert={data}
        showActions={false}
        showPem={true}
        embedded={true}
      />
    )
  }

  return null
}

/**
 * ActionBar — Toolbar under the window header with labeled action buttons
 */
function ActionBar({ onExport, hasPrivateKey, onRenew, onRevoke, onDelete, t }) {
  const btnBase = 'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium transition-all duration-150'

  return (
    <div className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 border-b border-border/40 bg-bg-tertiary/30">
      {/* Export actions with inline password */}
      <ExportActions 
        onExport={onExport} 
        hasPrivateKey={hasPrivateKey}
        className="!p-0 !bg-transparent !rounded-none"
      />

      {/* Renew */}
      {onRenew && (
        <button onClick={onRenew} className={cn(btnBase, 'text-text-secondary hover:text-accent-success hover:bg-accent-success/10')}>
          <ArrowsClockwise size={14} weight="duotone" />
          {t('common.renew', 'Renew')}
        </button>
      )}

      {/* Revoke */}
      {onRevoke && (
        <button onClick={onRevoke} className={cn(btnBase, 'text-text-secondary hover:text-status-warning hover:bg-status-warning/10')}>
          <X size={14} weight="bold" />
          {t('common.revoke', 'Revoke')}
        </button>
      )}

      {/* Spacer */}
      <div className="flex-1" />

      {/* Delete — right-aligned */}
      <button onClick={onDelete} className={cn(btnBase, 'text-text-tertiary hover:text-status-danger hover:bg-status-danger/10')}>
        <Trash size={14} weight="duotone" />
      </button>
    </div>
  )
}
