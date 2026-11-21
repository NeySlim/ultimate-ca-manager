/**
 * The Certificates zone's inspector: the mockup's dockFrame() under (or beside) the list, with the
 * certificates open in the inspector as its tabs (eight at most, « +N » beyond the width). A
 * certificate opened from another page comes here (InspectorContext), as the mockup's openCert().
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { Dock } from '../../../components/atelier'
import { useInspector } from '../../../contexts'
import { CertificateBody } from './CertificateBody'

// The certificate rows carry their id in data-open: its tab takes that key, so the focus finds the row back
const tabKey = (o) => String(o.entityId)

export function CertificateInspector() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { opened = [], activeKey, setActiveKey, closeEntity, closeAll } = useInspector()
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
  return (
    <Dock label={t('inspector.regionCertificate')} tabsLabel={t('inspector.certificatesLabel')}
      tabs={opened.map((o) => ({ key: tabKey(o), title: titles[o.key] || '…', icon: 'cert' }))}
      activeKey={tabKey(entry)} onSelectTab={(k) => setActiveKey(byTab[k]?.key)} onCloseTab={(k) => closeEntity(byTab[k]?.key)}
      onClose={() => closeAll({ refocus: true })}>
      <CertificateBody key={entry.key} entry={entry} onTitle={onTitle} onOpenCa={onOpenCa} section={section} onSection={setSection} />
    </Dock>
  )
}
