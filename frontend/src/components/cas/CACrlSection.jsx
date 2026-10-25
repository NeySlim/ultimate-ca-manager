/**
 * CACrlSection — revocation-list block for key-less/offline CAs (#302).
 *
 * UCM cannot sign a CRL for a CA whose key it does not hold (file-exported
 * offline CA, certificate-only import) or that is offline: the CRL is
 * generated next to the offline key and uploaded here instead. Shows the
 * currently served CRL (thisUpdate / nextUpdate / entry count, stale
 * warning) and the upload action. Renders nothing for CAs UCM signs for.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ListChecks, UploadSimple, Warning } from '@phosphor-icons/react'
import { Badge } from '../Badge'
import { Button } from '../Button'
import { CompactSection, CompactGrid, CompactField } from '../DetailCard'
import { UploadCRLModal } from '../../pages/cas/UploadCRLModal'
import { crlService } from '../../services'
import { usePermission } from '../../hooks'
import { formatDate, extractData } from '../../lib/utils'

export function CACrlSection({ ca }) {
  const { t } = useTranslation()
  const { canWrite } = usePermission()
  const [showUploadModal, setShowUploadModal] = useState(false)
  const [crlInfo, setCrlInfo] = useState(null)

  const eligible = !!ca && !ca.pending && (ca.offline || !ca.has_private_key)

  // extractData falls back to the whole response envelope when the API
  // returns data: null (no CRL yet) — only keep an actual CRL object
  const toCrlInfo = (response) => {
    const data = extractData(response)
    return data && data.crl_number != null ? data : null
  }

  useEffect(() => {
    let cancelled = false
    setCrlInfo(null)
    if (!eligible || !ca?.id) return undefined
    crlService.getForCA(ca.id)
      .then((response) => { if (!cancelled) setCrlInfo(toCrlInfo(response)) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [ca?.id, eligible])

  if (!eligible) return null

  const refresh = async () => {
    try {
      setCrlInfo(toCrlInfo(await crlService.getForCA(ca.id)))
    } catch { /* panel info only */ }
  }

  return (
    <>
      <CompactSection title={t('cas.crlSection')} icon={ListChecks} iconClass="icon-bg-cyan">
        <div className="space-y-2">
          {crlInfo ? (
            <>
              {crlInfo.is_stale && (
                <div className="rounded-lg px-3 py-2 bg-status-warning-op20 border border-status-warning-op40 flex items-start gap-2">
                  <Warning size={14} className="text-status-warning shrink-0 mt-0.5" />
                  <span className="text-2xs text-text-secondary">{t('cas.crlStaleWarning')}</span>
                </div>
              )}
              <CompactGrid>
                <CompactField label={t('crlOcsp.crlNumber')} value={String(crlInfo.crl_number ?? '—')} />
                <CompactField label={t('cas.crlEntries')} value={String(crlInfo.revoked_count ?? 0)} />
                <CompactField label={t('common.lastUpdate')} value={crlInfo.this_update ? formatDate(crlInfo.this_update) : '—'} />
                <CompactField label={t('crlOcsp.nextUpdate')} value={crlInfo.next_update ? formatDate(crlInfo.next_update) : '—'} />
              </CompactGrid>
              {crlInfo.is_external && (
                <Badge variant="info" size="sm">{t('cas.crlExternal')}</Badge>
              )}
            </>
          ) : (
            <p className="text-2xs text-text-secondary">{t('cas.crlNone')}</p>
          )}
          {canWrite('crl') && (
            <Button type="button" size="xs" variant="secondary" onClick={() => setShowUploadModal(true)}>
              <UploadSimple size={12} /> {t('cas.uploadCrl')}
            </Button>
          )}
        </div>
      </CompactSection>

      <UploadCRLModal
        open={showUploadModal}
        onClose={() => setShowUploadModal(false)}
        ca={ca}
        onSuccess={refresh}
      />
    </>
  )
}
