/**
 * An authority in a detached window: the side panel of the Authorities page (caSide()) over the
 * same reads (the authorities, the OCSP state, the cross certificates). An authority it links to
 * replaces it in the window; Issue opens the issue dialog there; a deletion closes the window.
 */
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { SkeletonPanel } from '../../components/atelier/Skeleton'
import { casService, crlService } from '../../services'
import { usePermission } from '../../hooks'
import { useOpenEntity } from '../../hooks/useOpenEntity'
import { IssueCertificateDialog } from '../certificates/IssueCertificateDialog'
import { CASide } from './CASide'
import { buildForest, nameOfCA } from './caTree'
import { useCrossLinks } from './useCrossLinks'

export default function CAFloat({ ids, idPrefix, onTitle, onClose, onReplace }) {
  const { t } = useTranslation()
  const { canRead } = usePermission()
  const openEntity = useOpenEntity()
  const id = Number(ids[0])
  const [cas, setCas] = useState(null)
  const [ocsp, setOcsp] = useState(null)
  const [issueCA, setIssueCA] = useState(null)
  const readCerts = canRead('certificates')

  useEffect(() => {
    let live = true
    const load = () => casService.getAll().then((res) => { if (live) setCas(res?.data || []) }).catch(() => { if (live) setCas((c) => c || false) })
    load()
    if (readCerts) crlService.getOcspStatus().then((res) => { if (live) setOcsp(res?.data || null) }).catch(() => {})
    const onChange = (e) => { if (e.detail?.type === 'ca') load() }
    window.addEventListener('ucm:data-changed', onChange)
    return () => { live = false; window.removeEventListener('ucm:data-changed', onChange) }
  }, [readCerts])

  const list = cas || []
  const forest = useMemo(() => buildForest(list), [cas]) // eslint-disable-line react-hooks/exhaustive-deps
  const crossLinks = useCrossLinks(list)
  const ca = forest.byId.get(id)
  useEffect(() => { if (ca) onTitle?.(nameOfCA(ca) || t('cas.unnamedCA')) }, [ca]) // eslint-disable-line react-hooks/exhaustive-deps

  if (cas === false || (cas && !ca)) return <p className="muted small float-note">{t('inspector.loadFailed')}</p>
  if (!ca) return <SkeletonPanel label={t('common.loading')} />
  return (
    <>
      <CASide key={ca.id} ca={ca} cas={list} forest={forest} crossLinks={crossLinks} ocsp={ocsp} idPrefix={idPrefix}
        onPick={(next) => onReplace?.([next])} onIssue={(c) => setIssueCA(c)} onCleared={onClose} />
      <IssueCertificateDialog open={!!issueCA} onOpenChange={(open) => { if (!open) setIssueCA(null) }} cas={list}
        initialData={issueCA ? { ca_id: issueCA.id } : null}
        onOpen={(issued) => { if (issued?.id) openEntity('certificate', issued.id) }} />
    </>
  )
}
