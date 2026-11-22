/**
 * The certificate in the dock: the mockup's inspector() body. The heading (icon, name, state badge,
 * Exporter, Renouveler when the certificate renews, « ⋯ »), the section tabs (Aperçu, Chaîne,
 * Extensions, Historique, then the product's PEM) and the panel. The actions and their dialogs
 * come from useEntityActions, with the zone's export, revocation and issue dialogs.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { DockBody, SkeletonPanel, Btn, IconBtn } from '../../../components/atelier'
import { useInspector, useNotification } from '../../../contexts'
import { usePermission } from '../../../hooks'
import { useFavorites } from '../../../hooks/useFavorites'
import { useEntityActions } from '../../../hooks/useEntityActions'
import { useAddIssuerToTrustStore } from './useAddIssuerToTrustStore'
import { useOpenCa } from './useOpenCa'
import { certificatesService } from '../../../services'
import { entityTitle } from '../../../lib/entityDetail'
import { extractCN, extractData } from '../../../lib/utils'
import { CertBadge } from '../CertBadge'
import { ExportDialog } from '../dialogs/ExportDialog'
import { RevokeDialog } from '../dialogs/RevokeDialog'
import { IssueCertificateDialog } from '../IssueCertificateDialog'
import { OverviewPanel } from './OverviewPanel'
import { ChainPanel } from './ChainPanel'
import { ExtensionsPanel } from './ExtensionsPanel'
import { HistoryPanel } from './HistoryPanel'
import { PemPanel } from './PemPanel'
import { CertMenu } from './CertMenu'
import { SECTIONS } from './certificateSections'

const DIALOGS = { Export: ExportDialog, Revoke: RevokeDialog, Issue: IssueCertificateDialog }
// The menu icons of the product's own actions, after the mockup's three
const MENU_ICONS = { lint: 'policy', uploadKey: 'upload', rename: 'file', unhold: 'refresh', keyRecovery: 'key', delete: 'close' }
const MENU_ORDER = ['lint', 'uploadKey', 'rename']
const menuRank = (id) => (MENU_ORDER.includes(id) ? MENU_ORDER.indexOf(id) : MENU_ORDER.length)

/**
 * entry: the inspector's { key, entityId, data }, whose data names its tab; the section is the dock's.
 * In a detached window: idPrefix keeps its ids apart from the dock's, onDone closes it after a deletion.
 */
export function CertificateBody({ entry, onOpenCa, section, onSection: setSection, idPrefix, onDone }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { closeEntity, openEntity, setEntityData } = useInspector()
  const { hasPermission } = usePermission()
  const { showSuccess, showError } = useNotification()
  const { isFavorite, toggleFavorite } = useFavorites('certificates')
  const { key, entityId } = entry
  const [cert, setCert] = useState(entry.data)
  const [loading, setLoading] = useState(!entry.data)
  const [failed, setFailed] = useState(false)
  const [menu, setMenu] = useState(false)

  useEffect(() => {
    if (cert) return undefined
    let cancelled = false
    setLoading(true)
    certificatesService.getById(entityId)
      .then((res) => { if (!cancelled) setCert(extractData(res) || res?.data || res) })
      .catch(() => { if (!cancelled) setFailed(true) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [entityId]) // eslint-disable-line react-hooks/exhaustive-deps

  // Kept in the context so switching tabs does not read it again, and its tab keeps its title
  useEffect(() => { if (cert && cert !== entry.data) setEntityData(key, cert) }, [cert]) // eslint-disable-line react-hooks/exhaustive-deps
  const title = cert ? entityTitle('certificate', cert, t) : ''

  const { actions, modals } = useEntityActions({
    type: 'certificate', entity: cert, entityId, onChanged: setCert, onClose: () => (onDone ? onDone() : closeEntity(key)), onOpenEntity: openEntity, dialogs: DIALOGS,
  })
  const openCa = useOpenCa(cert, onOpenCa)
  const trust = useAddIssuerToTrustStore(cert, setCert)

  if (loading || !cert) {
    return (
      <div className="dock-body">
        <div className="detail-panel" id={`${idPrefix || ''}detail-panel`} aria-busy={loading || undefined}>
          {loading ? <SkeletonPanel label={t('common.loading')} /> : <p className="muted small">{failed ? t('inspector.loadFailed') : t('common.notFound', 'Not found')}</p>}
        </div>
      </div>
    )
  }

  const visible = actions.filter((a) => a.visible && a.inBar !== false)
  const exportAction = visible.find((a) => a.id === 'export')
  const renewAction = visible.find((a) => a.id === 'renew')
  const revoke = visible.find((a) => a.id === 'revoke')
  const others = visible.filter((a) => !['export', 'renew', 'revoke'].includes(a.id))
  const revoked = !!cert.revoked
  const commonName = cert.common_name || cert.cn || title
  const copyName = async () => {
    try {
      await navigator.clipboard.writeText(commonName)
      showSuccess(t('inspector.cert.nameCopied'))
    } catch {
      showError(t('inspector.cert.copyFailed'))
    }
  }
  const favorite = isFavorite(cert.id)
  const items = [
    { id: 'copy', icon: 'copy', label: t('inspector.cert.copyName'), onClick: copyName },
    // The journal searches its entries' text: the common name finds this certificate's
    hasPermission('read:audit') && { id: 'activity', icon: 'activity', label: t('inspector.cert.viewActivity'), onClick: () => navigate(`/audit?search=${encodeURIComponent(commonName)}`) },
    revoke && { id: 'revoke', icon: 'block', label: t('inspector.cert.revokeAction'), danger: true, write: true, onClick: revoke.onClick },
    ...others.filter((a) => !a.danger).sort((a, b) => menuRank(a.id) - menuRank(b.id))
      .map((a) => ({ id: a.id, icon: MENU_ICONS[a.id] || 'cert', label: a.label, onClick: a.onClick, write: a.id !== 'lint' })),
    { id: 'favorite', icon: 'pin', label: favorite ? t('inspector.cert.unfavorite') : t('inspector.cert.favorite'),
      onClick: () => toggleFavorite({ id: cert.id, name: title, subtitle: cert.issuer ? extractCN(cert.issuer) : '' }) },
    trust.offered && { id: 'trust', icon: 'shield', label: t('details.addIssuerToTrustStore'), write: true, onClick: trust.add },
    ...others.filter((a) => a.danger).map((a) => ({ id: a.id, icon: MENU_ICONS[a.id] || 'close', label: a.label, danger: true, write: true, onClick: a.onClick })),
  ].filter(Boolean)

  return (
    <>
      <DockBody icon="cert" title={title} badge={<CertBadge cert={cert} t={t} />}
        actions={(
          <>
            {exportAction && <Btn tone={revoked || !renewAction ? 'primary' : undefined} write={false} icon="download" data-export={cert.id} onClick={exportAction.onClick}>{t('export.title')}</Btn>}
            {renewAction && <Btn tone="primary" icon="refresh" data-renew={cert.id} onClick={renewAction.onClick}>{t('common.renew')}</Btn>}
            <IconBtn quiet icon="more" title={false} label={t('inspector.moreActions', { name: title })} data-cert-menu={cert.id} onClick={() => setMenu(true)} />
          </>
        )}
        sections={SECTIONS.map((s) => [s, t(`inspector.sections.${s}`)])} section={section} onSection={setSection} sectionsLabel={t('inspector.certificateSections')}
        idPrefix={idPrefix}>
        {section === 'overview' && <OverviewPanel cert={cert} title={title} openCa={openCa} onOpenRelated={(id) => openEntity('certificate', id)} />}
        {section === 'chain' && <ChainPanel cert={cert} title={title} openCa={openCa} onChanged={setCert} />}
        {section === 'extensions' && <ExtensionsPanel cert={cert} />}
        {section === 'history' && <HistoryPanel cert={cert} />}
        {section === 'pem' && <PemPanel cert={cert} />}
      </DockBody>
      {menu && <CertMenu name={commonName} items={items} revoked={revoked} onClose={() => setMenu(false)} />}
      {modals}
    </>
  )
}
