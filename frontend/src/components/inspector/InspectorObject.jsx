/**
 * InspectorObject: loads one opened entity, then renders the shared action bar,
 * the section tabs and the pure detail panel; the actions themselves live in
 * hooks/useEntityActions. The action modals are returned beside the body so
 * they sit outside the dock region.
 */
import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { CertificatePanel } from '../detail/CertificatePanel'
import { CAPanel } from '../detail/CAPanel'
import { TrustCertPanel } from '../detail/TrustCertPanel'
import { ActionBar } from '../detail/ActionBar'
import { useInspector } from '../../contexts/InspectorContext'
import { usePermission } from '../../hooks'
import { useEntityActions } from '../../hooks/useEntityActions'
import { entityTitle, entitySubtitle } from '../../lib/entityDetail'
import { extractData } from '../../lib/utils'
import { LoadingSpinner } from '../LoadingSpinner'
import { cn } from '../../lib/utils'
import { INSPECTOR_TYPES } from './config'
import { SectionTabs, tabId, panelId } from './InspectorTabs'

export function InspectorObject({ entry, onTitle }) {
  const { t } = useTranslation()
  const { closeEntity, openEntity, setEntityData } = useInspector()
  const { canWrite, hasPermission } = usePermission()
  const { key, type, entityId } = entry
  const config = INSPECTOR_TYPES[type]
  const [data, setData] = useState(entry.data)
  const [loading, setLoading] = useState(!entry.data)
  const [failed, setFailed] = useState(false)
  const [section, setSection] = useState('overview')

  useEffect(() => {
    if (!config || data) return
    let cancelled = false
    setLoading(true)
    config.fetchById(entityId)
      .then((res) => { if (!cancelled) setData(extractData(res) || res.data || res) })
      .catch(() => { if (!cancelled) setFailed(true) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [entityId, type]) // eslint-disable-line react-hooks/exhaustive-deps

  // The loaded entity is kept in the context so switching tabs does not reload it
  useEffect(() => { if (data && data !== entry.data) setEntityData(key, data) }, [data]) // eslint-disable-line react-hooks/exhaustive-deps

  const title = data ? entityTitle(type, data, t) : ''
  useEffect(() => { if (title) onTitle(key, title) }, [title, key]) // eslint-disable-line react-hooks/exhaustive-deps

  const { actions, modals, handler } = useEntityActions({
    type, entity: data, entityId, onChanged: setData, onClose: () => closeEntity(key),
  })

  if (!config) return null
  const Icon = config.icon
  const sections = config.sections

  return (
    <>
      <div role="tabpanel" id={panelId(key)} aria-labelledby={tabId(key)} className="flex-1 min-h-0 flex flex-col">
        {loading ? (
          <div className="flex-1 flex items-center justify-center"><LoadingSpinner size="md" /></div>
        ) : data ? (
          <>
            <div className="shrink-0 flex items-center gap-2 px-3 py-2">
              <div className={cn('p-1.5 rounded-lg shrink-0', config.iconClass)}><Icon size={16} weight="duotone" /></div>
              <div className="min-w-0">
                <h2 className="text-sm font-semibold text-text-primary truncate">{title}</h2>
                <p className="text-xs text-text-tertiary truncate">{entitySubtitle(type, data, t)}</p>
              </div>
            </div>
            <ActionBar actions={actions} />
            <SectionTabs objectKey={key} sections={sections} current={section} onSelect={setSection} />
            <div role="tabpanel" id={`${panelId(key)}-section`} aria-labelledby={`${tabId(key)}-${section}`}
              className="flex-1 min-h-0 overflow-y-auto">
              {type === 'ca' ? (
                <CAPanel ca={data} embedded section={section} onImportKey={handler('importKey')} onCaChanged={setData}
                  canWriteCas={canWrite('cas')} canAttachProfile={canWrite('cas') && hasPermission('admin:system')} />
              ) : type === 'truststore' ? (
                <TrustCertPanel cert={data} embedded section={section} />
              ) : (
                <CertificatePanel certificate={data} embedded section={section}
                  onOpenRelated={type === 'certificate' ? (id) => openEntity('certificate', id) : undefined} />
              )}
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center text-text-tertiary text-sm">
            {failed ? t('inspector.loadFailed') : t('common.notFound', 'Not found')}
          </div>
        )}
      </div>
      {modals}
    </>
  )
}
