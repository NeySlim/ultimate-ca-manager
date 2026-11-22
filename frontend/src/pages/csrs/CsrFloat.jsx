/**
 * A request in a detached window: its sections as the dock shows them, read by GET /csrs/:id.
 * Signing and the other actions stay with the dock of the requests page.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { DockBody } from '../../components/atelier/Dock'
import { SkeletonPanel } from '../../components/atelier/Skeleton'
import { csrsService } from '../../services'
import { extractData } from '../../lib/utils'
import { CsrSections, csrName, csrPill, csrSections, csrSigned } from './CsrSections'

export default function CsrFloat({ ids, idPrefix, onTitle }) {
  const { t } = useTranslation()
  const id = ids[0]
  const [csr, setCsr] = useState(null)
  const [section, setSection] = useState('overview')
  useEffect(() => {
    let live = true
    csrsService.getById(id).then((res) => { if (live) setCsr(extractData(res) || false) }).catch(() => { if (live) setCsr(false) })
    return () => { live = false }
  }, [id])
  useEffect(() => { if (csr) onTitle?.(csrName(t, csr)) }, [csr]) // eslint-disable-line react-hooks/exhaustive-deps

  if (csr === false) return <p className="muted small float-note">{t('inspector.loadFailed')}</p>
  if (!csr) return <SkeletonPanel label={t('common.loading')} />
  // The detail of a request carries its certificate's dates once signed
  const signed = csrSigned(csr, Boolean(csr.valid_to))
  return (
    <DockBody icon="file" title={csrName(t, csr)} badge={csrPill(t, csr, signed)} section={section} onSection={setSection}
      sectionsLabel={t('atelier.sectionsOf', { name: csrName(t, csr) })} sections={csrSections(t, signed)} idPrefix={idPrefix}>
      <CsrSections csr={csr} signed={signed} section={section} />
    </DockBody>
  )
}
