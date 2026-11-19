/**
 * InspectorObject: loads one opened entity, then renders its heading, its section tabs
 * and its detail. A certificate has its own detail (CertificateDetail); the other types
 * keep the shared action bar over their pure panel. The actions live in
 * hooks/useEntityActions; their modals are returned beside the body.
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
import { INSPECTOR_TYPES } from './config'
import { SectionTabs, tabId, panelId } from './InspectorTabs'
import { CertificateDetail } from './certificate/CertificateDetail'

// Bars standing for the three columns of a detail while it loads
function PanelSkeleton({ label }) {
  return (
    <div className="insp-panel" aria-busy="true">
      <div className="insp-sk-panel" aria-hidden="true">
        {[0, 1, 2].map((c) => (
          <div key={c} className="insp-sk-col">
            <span className="insp-sk" style={{ width: '40%' }} />
            {[0, 1, 2, 3].map((i) => <span key={i} className="insp-sk" style={{ width: `${45 + ((i + c) * 37) % 45}%` }} />)}
          </div>
        ))}
      </div>
      <p className="sr-only" role="status">{label}</p>
    </div>
  )
}

export function InspectorObject({ entry, onTitle, layout = 'columns' }) {
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
  const subtitle = data ? entitySubtitle(type, data, t) : ''

  return (
    <>
      <div role="tabpanel" id={panelId(key)} aria-labelledby={tabId(key)} className="insp-body">
        {loading ? (
          <PanelSkeleton label={t('inspector.loading')} />
        ) : data && type === 'certificate' ? (
          <CertificateDetail objectKey={key} certificate={data} title={title} actions={actions} layout={layout}
            onChanged={setData} onOpen={openEntity} />
        ) : data ? (
          <>
            <header className="insp-heading">
              <div className="insp-title">
                <Icon aria-hidden="true" />
                <h2>{title}</h2>
                {subtitle && <span className="insp-subtitle">{subtitle}</span>}
              </div>
            </header>
            <ActionBar actions={actions} />
            <SectionTabs objectKey={key} sections={sections} current={section} onSelect={setSection} />
            <div role="tabpanel" id={`${panelId(key)}-section`} aria-labelledby={`${tabId(key)}-${section}`}
              className="insp-panel is-plain">
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
        ) : (
          <div className="insp-note">{failed ? t('inspector.loadFailed') : t('common.notFound', 'Not found')}</div>
        )}
      </div>
      {modals}
    </>
  )
}
