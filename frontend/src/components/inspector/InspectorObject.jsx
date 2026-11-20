/**
 * InspectorObject: loads one opened entity and renders its body in the dock. A
 * certificate gets the Atelier detail (heading, actions, Overview, Chain,
 * Extensions, History, PEM); the other types keep their panel under the same
 * heading. The actions live in hooks/useEntityActions; their modals are returned
 * beside the body.
 */
import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { CAPanel } from '../detail/CAPanel'
import { TrustCertPanel } from '../detail/TrustCertPanel'
import { CertificatePanel } from '../detail/CertificatePanel'
import { ActionBar } from '../detail/ActionBar'
import { useInspector } from '../../contexts/InspectorContext'
import { usePermission } from '../../hooks'
import { useEntityActions } from '../../hooks/useEntityActions'
import { entityTitle, entitySubtitle } from '../../lib/entityDetail'
import { extractData } from '../../lib/utils'
import { INSPECTOR_TYPES } from './config'
import { SectionTabs, tabId, panelId } from './InspectorTabs'
import { CertificateDetail } from './certificate/CertificateDetail'
import { DetailSkeleton } from './certificate/DetailSkeleton'

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

  let body
  if (loading) body = <DetailSkeleton />
  else if (!data) body = <div className="ins-empty">{failed ? t('inspector.loadFailed') : t('common.notFound', 'Not found')}</div>
  else if (type === 'certificate') {
    body = (
      <CertificateDetail cert={data} objectKey={key} title={title} actions={actions} section={section}
        onSection={setSection} onChanged={setData} onOpenRelated={(id) => openEntity('certificate', id)}
        onOpenCa={(id) => openEntity('ca', id)} />
    )
  } else {
    body = (
      <>
        <header className="ins-heading">
          <div className="ins-title">
            <Icon className="ins-title-icon" weight="duotone" aria-hidden="true" />
            <div className="min-w-0">
              <h2>{title}</h2>
              <p className="ins-subtitle">{entitySubtitle(type, data, t)}</p>
            </div>
          </div>
        </header>
        <div className="ins-legacy-actions"><ActionBar actions={actions} /></div>
        <SectionTabs objectKey={key} sections={config.sections} current={section} onSelect={setSection} />
        <div role="tabpanel" id={`${panelId(key)}-section`} aria-labelledby={`${tabId(key)}-${section}`} className="ins-legacy">
          {type === 'ca' ? (
            <CAPanel ca={data} embedded section={section} onImportKey={handler('importKey')} onCaChanged={setData}
              canWriteCas={canWrite('cas')} canAttachProfile={canWrite('cas') && hasPermission('admin:system')} />
          ) : type === 'truststore' ? (
            <TrustCertPanel cert={data} embedded section={section} />
          ) : (
            <CertificatePanel certificate={data} embedded section={section} />
          )}
        </div>
      </>
    )
  }

  return (
    <>
      <div role="tabpanel" id={panelId(key)} aria-labelledby={tabId(key)} className="ins-object">
        {body}
      </div>
      {modals}
    </>
  )
}
