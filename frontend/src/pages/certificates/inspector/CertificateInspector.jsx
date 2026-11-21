/**
 * The Certificates zone's inspector: the mockup's dockFrame() under (or beside) the list, with the
 * certificates open in the inspector as its tabs (eight at most, « +N » beyond the width). A
 * certificate opened from another page comes here (InspectorContext), as the mockup's openCert().
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useLocation, useNavigate } from 'react-router-dom'
import { pageOf } from '../../../lib/pageOf'
import { Dock } from '../../../components/atelier'
import { useDockParam, asId } from '../../../components/atelier/useDockParam'
import { useInspector } from '../../../contexts'
import { CertificateBody } from './CertificateBody'
import { SECTIONS } from './certificateSections'

// The certificate rows carry their id in data-open: its tab takes that key, so the focus finds the row back
const tabKey = (o) => String(o.entityId)

export function CertificateInspector() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { opened = [], activeKey, setActiveKey, openEntity, closeEntity, closeAll } = useInspector()
  const [titles, setTitles] = useState({})
  // The active certificate and its section live in the URL (`item`, `section`), as every dock's object
  const { item, section, setSection, open: openInUrl, close: closeInUrl } = useDockParam({ sections: SECTIONS })
  const active = opened.find((o) => o.key === activeKey) || opened[0]
  const activeId = active ? String(active.entityId) : null
  // Whichever moved last leads: the URL (a link, a reload, Back) or the inspector (a row, a tab, a close)
  const seen = useRef({ item: undefined, activeId: undefined, count: 0 })
  const here = pageOf(useLocation().pathname) === '/certificates'
  useEffect(() => {
    const prev = seen.current
    seen.current = { item, activeId, count: opened.length }
    // Another page's URL (the Trust Store an action leads to) says nothing of this dock
    if (!here || item === activeId) return
    if (item !== prev.item && (prev.item !== undefined || item != null)) {
      const tab = opened.find((o) => String(o.entityId) === item)
      if (item == null) closeAll()
      else if (tab) setActiveKey(tab.key)
      else openEntity('certificate', asId(item))
    } else if (activeId == null) closeInUrl()
    // A certificate newly opened starts on Aperçu, as the mockup's openCert(); a tab switch keeps the section
    else openInUrl(activeId, opened.length > prev.count || prev.activeId == null ? {} : { section })
  }, [item, activeId, here]) // eslint-disable-line react-hooks/exhaustive-deps
  const onTitle = useCallback((key, title) => setTitles((prev) => (prev[key] === title ? prev : { ...prev, [key]: title })), [])
  // An authority opens in its own zone, as the mockup's « Inspecter l'autorité » goes to the authorities
  const onOpenCa = useCallback((id) => navigate(`/cas/${id}`), [navigate])

  if (!opened.length) return null
  const entry = opened.find((o) => o.key === activeKey) || opened[0]
  const byTab = Object.fromEntries(opened.map((o) => [tabKey(o), o]))
  return (
    <Dock label={t('inspector.regionCertificate')} tabsLabel={t('inspector.certificatesLabel')}
      tabs={opened.map((o) => ({ key: tabKey(o), title: titles[o.key] || '…', icon: 'cert' }))}
      activeKey={tabKey(entry)} onSelectTab={(k) => setActiveKey(byTab[k]?.key)} onCloseTab={(k) => closeEntity(byTab[k]?.key)}
      onClose={() => closeAll({ refocus: true })}>
      <CertificateBody key={entry.key} entry={entry} onTitle={onTitle} onOpenCa={onOpenCa} section={section} onSection={setSection} />
    </Dock>
  )
}
