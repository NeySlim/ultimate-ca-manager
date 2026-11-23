/**
 * The Certificates zone's inspector: the mockup's dockFrame() under (or beside) the list, with the
 * certificates open in the inspector as its tabs (eight at most, « +N » beyond the width). A
 * certificate opened from another page comes here (InspectorContext), as the mockup's openCert().
 */
import { useCallback, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useLocation, useNavigate } from 'react-router-dom'
import { pageOf } from '../../../lib/pageOf'
import { Dock } from '../../../components/atelier'
import { useDockParam, asId } from '../../../components/atelier/useDockParam'
import { useInspector } from '../../../contexts'
import { useDetached } from '../../../components/detached/useDetached'
import { certificatesService } from '../../../services'
import { entityTitle } from '../../../lib/entityDetail'
import { extractData } from '../../../lib/utils'
import { CertificateBody } from './CertificateBody'
import { SECTIONS } from './certificateSections'

const ALIASES = ['id']

// The certificate rows carry their id in data-open: its tab takes that key, so the focus finds the row back
const tabKey = (o) => String(o.entityId)
// One certificate open is `item` alone; several are listed in `open` as well
const urlList = (ids) => (ids.length > 1 ? ids : [])

export function CertificateInspector() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const detached = useDetached()
  const { opened = [], activeKey, setActiveKey, openEntity, closeEntity, closeAll, setEntityData } = useInspector()
  // The active certificate and its section live in the URL (`item`, `section`), as every dock's object, and the open ones in `open`;
  // `id` is the former name of the item in links (`/certificates?id=N`)
  const { item, section, list, setSection, setList, open: openInUrl, close: closeInUrl } = useDockParam({ sections: SECTIONS, list: true, aliases: ALIASES })
  const active = opened.find((o) => o.key === activeKey) || opened[0]
  const activeId = active ? String(active.entityId) : null
  const ids = opened.map(tabKey)
  const idsKey = ids.join(',')
  const listKey = list.join(',')
  // Whichever moved last leads: the URL (a link, a reload, Back) or the inspector (a row, a tab, a close)
  const seen = useRef({ item: undefined, activeId: undefined, count: 0, list: undefined })
  const here = pageOf(useLocation().pathname) === '/certificates'
  useEffect(() => {
    const prev = seen.current
    seen.current = { item, activeId, count: opened.length, list: listKey }
    // Another page's URL (the Trust Store an action leads to) says nothing of this dock
    if (!here) return
    // A list the URL brings (a reload, a link) opens its certificates, the inspector keeping eight; the URL's item stays the active one
    const missing = listKey !== prev.list ? list.filter((id) => !ids.includes(id)) : []
    if (missing.length) {
      for (const id of missing) openEntity('certificate', asId(id))
      if (item != null) openEntity('certificate', asId(item))
      return
    }
    if (item === activeId) {
      if (activeId != null && listKey !== urlList(ids).join(',')) setList(urlList(ids))
      return
    }
    if (item !== prev.item && (prev.item !== undefined || item != null)) {
      const tab = opened.find((o) => String(o.entityId) === item)
      if (item == null) closeAll()
      else if (tab) setActiveKey(tab.key)
      else openEntity('certificate', asId(item))
    } else if (activeId == null) closeInUrl()
    // A certificate newly opened starts on Aperçu, as the mockup's openCert(); a tab switch keeps the section
    else openInUrl(activeId, { ...(opened.length > prev.count || prev.activeId == null ? {} : { section }), list: urlList(ids) })
  }, [item, activeId, here, listKey, idsKey]) // eslint-disable-line react-hooks/exhaustive-deps

  // A tab the URL reopened without showing it reads its certificate, so it is named; the shown one reads its own
  const asked = useRef(new Set())
  useEffect(() => {
    for (const k of [...asked.current]) if (!opened.some((o) => o.key === k)) asked.current.delete(k)
    for (const o of opened) {
      if (o.data || o === active || asked.current.has(o.key)) continue
      asked.current.add(o.key)
      certificatesService.getById(o.entityId)
        .then((res) => { const cert = extractData(res) || res?.data; if (cert) setEntityData(o.key, cert) })
        .catch(() => {})
    }
  }, [idsKey, active?.key]) // eslint-disable-line react-hooks/exhaustive-deps

  // An authority opens in its own zone, as the mockup's « Inspecter l'autorité » goes to the authorities
  const onOpenCa = useCallback((id) => navigate(`/cas/${id}`), [navigate])

  if (!opened.length) return null
  const entry = active
  const byTab = Object.fromEntries(opened.map((o) => [tabKey(o), o]))
  // The title comes with the open entry (its certificate, kept in the inspector): it outlives this page
  return (
    <Dock label={t('inspector.regionCertificate')} tabsLabel={t('inspector.certificatesLabel')}
      tabs={opened.map((o) => ({ key: tabKey(o), title: o.data ? entityTitle('certificate', o.data, t) : '…', icon: 'cert' }))}
      activeKey={tabKey(entry)} onSelectTab={(k) => setActiveKey(byTab[k]?.key)} onCloseTab={(k) => closeEntity(byTab[k]?.key)}
      onClose={() => closeAll({ refocus: true })}
      // Detached, the certificate leaves the dock for a window of its own
      onDetach={detached?.available ? () => { detached.open('certificate', [entry.entityId]); closeEntity(entry.key) } : undefined}>
      <CertificateBody key={entry.key} entry={entry} onOpenCa={onOpenCa} section={section} onSection={setSection} />
    </Dock>
  )
}
