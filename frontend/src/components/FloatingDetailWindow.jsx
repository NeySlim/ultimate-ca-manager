/**
 * FloatingDetailWindow: container of an entity detail window. Loads the
 * entity, then renders the shared action bar and the pure detail panel; the
 * actions themselves live in hooks/useEntityActions.
 */
import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Certificate, ShieldCheck, Fingerprint } from '@phosphor-icons/react'
import { FloatingWindow } from './ui/FloatingWindow'
import { CertificatePanel } from './detail/CertificatePanel'
import { CAPanel } from './detail/CAPanel'
import { TrustCertPanel } from './detail/TrustCertPanel'
import { ActionBar } from './detail/ActionBar'
import { certificatesService, casService, truststoreService, userCertificatesService } from '../services'
import { useWindowManager } from '../contexts/WindowManagerContext'
import { usePermission } from '../hooks'
import { useEntityActions } from '../hooks/useEntityActions'
import { entityTitle, entitySubtitle } from '../lib/entityDetail'
import { extractData } from '../lib/utils'
import { LoadingSpinner } from './LoadingSpinner'

const ENTITY_CONFIG = {
  certificate: {
    icon: Certificate,
    iconClass: 'bg-accent-primary-op15 text-accent-primary',
    fetchById: (id) => certificatesService.getById(id),
  },
  ca: {
    icon: ShieldCheck,
    iconClass: 'bg-accent-success-op15 text-accent-success',
    fetchById: (id) => casService.getById(id),
  },
  truststore: {
    icon: Fingerprint,
    iconClass: 'bg-accent-warning-op15 text-accent-warning',
    fetchById: (id) => truststoreService.getById(id),
  },
  user_certificate: {
    icon: Certificate,
    iconClass: 'bg-accent-primary-op15 text-accent-primary',
    fetchById: (id) => userCertificatesService.getById(id),
  },
}

export function FloatingDetailWindow({ windowInfo }) {
  const { t } = useTranslation()
  const { closeWindow, focusWindow, sameWindow, openWindow } = useWindowManager()
  const { canWrite, hasPermission } = usePermission()
  const [data, setData] = useState(windowInfo.data?.fullData || null)
  const [loading, setLoading] = useState(!windowInfo.data?.fullData)
  const [minimized, setMinimized] = useState(false)

  const config = ENTITY_CONFIG[windowInfo.type]

  useEffect(() => {
    if (!config || data) return
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

  const { actions, modals, handler } = useEntityActions({
    type: windowInfo.type,
    entity: data,
    entityId: windowInfo.entityId,
    onChanged: setData,
    onClose: () => closeWindow(windowInfo.id),
  })

  if (!config) return null

  const title = data ? entityTitle(windowInfo.type, data, t) : t('common.loading')
  const subtitle = data ? entitySubtitle(windowInfo.type, data, t) : ''
  const isCert = windowInfo.type === 'certificate'

  return (
    <>
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
          <ActionBar actions={actions} />
          <div className="flex-1 overflow-y-auto p-0">
            {windowInfo.type === 'ca' ? (
              <CAPanel
                ca={data}
                embedded
                onImportKey={handler('importKey')}
                onCaChanged={setData}
                canWriteCas={canWrite('cas')}
                canAttachProfile={canWrite('cas') && hasPermission('admin:system')}
              />
            ) : windowInfo.type === 'truststore' ? (
              <TrustCertPanel cert={data} embedded />
            ) : (
              <CertificatePanel
                certificate={data}
                embedded
                onOpenRelated={isCert ? (id) => openWindow('certificate', id) : undefined}
              />
            )}
          </div>
        </>
      ) : (
        <div className="flex-1 flex items-center justify-center text-text-tertiary text-sm">
          {t('common.notFound', 'Not found')}
        </div>
      )}
    </FloatingWindow>
    {modals}
    </>
  )
}
