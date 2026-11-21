/**
 * The Certificates zone's inspector: the mockup's dockFrame() under (or beside) the list, with the
 * objects open in the inspector as its tabs (eight at most, « +N » beyond the width). It claims
 * the shell's dock while the page is on screen. A certificate gets the mockup's body; another
 * object opened from here keeps the product's panel until its own zone draws it.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { Dock } from '../../../components/atelier'
import { useInspector } from '../../../contexts'
import { InspectorObject } from '../../../components/inspector/InspectorObject'
import { CertificateBody } from './CertificateBody'

const ICONS = { certificate: 'cert', ca: 'shield', truststore: 'anchor', user_certificate: 'cert', approval: 'approve', key_recovery: 'key', report: 'chart' }
// The certificate rows carry their id in data-open: its tab takes that key, so the focus finds the row back
const tabKey = (o) => (o.type === 'certificate' ? String(o.entityId) : o.key)

export function CertificateInspector() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const ins = useInspector()
  // The shell's dock steps aside while the zone draws its own
  const { claimDock } = ins
  useEffect(() => claimDock?.(), [claimDock])
  const { opened = [], activeKey, setActiveKey, closeEntity, closeAll, height, width, position, setGeometry, collapsed, setCollapsed } = ins
  const [titles, setTitles] = useState({})
  const [section, setSection] = useState('overview')
  const count = useRef(opened.length)
  // A certificate newly opened starts on Aperçu, as the mockup's openCert()
  useEffect(() => {
    if (opened.length > count.current) setSection('overview')
    count.current = opened.length
  }, [opened.length])
  const onTitle = useCallback((key, title) => setTitles((prev) => (prev[key] === title ? prev : { ...prev, [key]: title })), [])
  // An authority opens in its own zone, as the mockup's « Inspecter l'autorité » goes to the authorities
  const onOpenCa = useCallback((id) => navigate(`/cas/${id}`), [navigate])

  if (!opened.length) return null
  const entry = opened.find((o) => o.key === activeKey) || opened[0]
  const byTab = Object.fromEntries(opened.map((o) => [tabKey(o), o]))
  const certs = opened.every((o) => o.type === 'certificate')
  return (
    <Dock label={t(certs ? 'inspector.regionCertificate' : 'inspector.region')} tabsLabel={t(certs ? 'inspector.certificatesLabel' : 'inspector.objectsLabel')}
      tabs={opened.map((o) => ({ key: tabKey(o), title: titles[o.key] || '…', icon: ICONS[o.type] || 'cert' }))}
      activeKey={tabKey(entry)} onSelectTab={(k) => setActiveKey(byTab[k]?.key)} onCloseTab={(k) => closeEntity(byTab[k]?.key)}
      onClose={() => closeAll({ refocus: true })}
      geometry={{ height, width, side: position }} onGeometry={(p) => setGeometry(p.side ? { position: p.side } : p)}
      collapsed={collapsed} onCollapsed={setCollapsed}>
      {entry.type === 'certificate' ? (
        <CertificateBody key={entry.key} entry={entry} onTitle={onTitle} onOpenCa={onOpenCa} section={section} onSection={setSection} />
      ) : (
        <div className="dock-body atl-out"><InspectorObject key={entry.key} entry={entry} onTitle={onTitle} /></div>
      )}
    </Dock>
  )
}
