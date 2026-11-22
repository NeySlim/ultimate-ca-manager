/**
 * A certificate in a detached window: the inspector's body (heading, actions, sections) with a
 * section of its own; the window takes the certificate's name once read, and closes when the
 * certificate is deleted. An authority opens in its own page, as from the dock.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { SkeletonPanel } from '../../components/atelier/Skeleton'
import { certificatesService } from '../../services'
import { entityTitle } from '../../lib/entityDetail'
import { extractData } from '../../lib/utils'
import { CertificateBody } from './inspector/CertificateBody'

export default function CertificateFloat({ ids, idPrefix, onTitle, onClose }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const id = ids[0]
  const [cert, setCert] = useState(null)
  const [section, setSection] = useState('overview')

  useEffect(() => {
    let live = true
    certificatesService.getById(id)
      .then((res) => { const data = extractData(res) || res?.data || res; if (live) setCert(data || false) })
      .catch(() => { if (live) setCert(false) })
    return () => { live = false }
  }, [id])
  useEffect(() => { if (cert) onTitle?.(entityTitle('certificate', cert, t)) }, [cert]) // eslint-disable-line react-hooks/exhaustive-deps

  if (cert === false) return <p className="muted small float-note">{t('inspector.loadFailed')}</p>
  if (!cert) return <SkeletonPanel label={t('common.loading')} />
  return (
    <CertificateBody entry={{ key: `detached:${id}`, entityId: id, data: cert }} section={section} onSection={setSection}
      onOpenCa={(caId) => navigate(`/cas/${caId}`)} idPrefix={idPrefix} onDone={onClose} />
  )
}
