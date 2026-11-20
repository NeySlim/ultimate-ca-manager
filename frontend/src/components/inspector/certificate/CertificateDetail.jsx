/**
 * Certificate in the inspector, after the Atelier detail: heading (icon, name,
 * state, Export, Renew when it applies, « ⋯ » for the other actions), then the
 * Overview, Chain, Extensions, History and PEM sections. The « ⋯ » dialog lists the
 * actions of the mockup first (copy the name, its activity, revoke), then the
 * product's own, deletion last.
 */
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { Certificate, DownloadSimple, Star, Copy, Pulse, Prohibit, ShieldCheck } from '@phosphor-icons/react'
import { useNotification } from '../../../contexts'
import { usePermission } from '../../../hooks'
import { RefreshIcon } from '../../list/atelierIcons'
import { useAddIssuerToTrustStore } from './CertificateChain'
import { useFavorites } from '../../../hooks/useFavorites'
import { StatusPill } from '../../list'
import { certificateState } from '../../../pages/certificates/useCertificateColumns'
import { extractCN, cn } from '../../../lib/utils'
import { SectionTabs, tabId, panelId } from '../InspectorTabs'
import { INSPECTOR_TYPES } from '../config'
import { useDockPlacementContext } from '../placement'
import { MoreActionsMenu } from './MoreActionsMenu'
import { CertificateOverview } from './CertificateOverview'
import { CertificateChain } from './CertificateChain'
import { CertificateExtensionList } from './CertificateExtensionList'
import { CertificateHistory } from './CertificateHistory'
import { CertificatePem } from './CertificatePem'
import { useOpenCa } from './useOpenCa'
import '../../list/list.css'

// Actions that stay buttons of the heading; every other visible action goes to the menu
// The mockup's order after copy, activity and revoke: lint, key upload, rename, then the product's others
const MENU_ORDER = ['lint', 'uploadKey', 'rename']
const menuRank = (id) => (MENU_ORDER.includes(id) ? MENU_ORDER.indexOf(id) : MENU_ORDER.length)
const BUTTONS = ['export', 'renew']

export function CertificateDetail({ cert, objectKey, title, actions, section, onSection, onChanged, onOpenRelated, onOpenCa }) {
  const { t } = useTranslation()
  const placement = useDockPlacementContext()
  const columns = placement === 'bottom' ? 3 : 1
  const { isFavorite, toggleFavorite } = useFavorites('certificates')
  const { hasPermission } = usePermission()
  const { showSuccess, showError } = useNotification()
  const navigate = useNavigate()
  const openCa = useOpenCa(cert, onOpenCa)
  const trust = useAddIssuerToTrustStore(cert, onChanged)

  const visible = actions.filter((a) => a.visible && a.inBar !== false)
  const exportAction = visible.find((a) => a.id === 'export')
  const renewAction = visible.find((a) => a.id === 'renew')
  const favorite = isFavorite(cert.id)
  const others = visible.filter((a) => !BUTTONS.includes(a.id))
  const revoke = others.find((a) => a.id === 'revoke')
  const commonName = cert.common_name || cert.cn || title
  const copyName = async () => {
    try {
      await navigator.clipboard.writeText(commonName)
      showSuccess(t('inspector.cert.nameCopied'))
    } catch {
      showError(t('inspector.cert.copyFailed'))
    }
  }
  const menu = [
    { id: 'copy', icon: Copy, label: t('inspector.cert.copyName'), onClick: copyName },
    // The audit list searches its entries' text; the common name finds this certificate's
    ...(hasPermission('read:audit') ? [{
      id: 'activity', icon: Pulse, label: t('inspector.cert.viewActivity'),
      onClick: () => navigate(`/audit?search=${encodeURIComponent(commonName)}`),
    }] : []),
    ...(revoke ? [{ ...revoke, icon: Prohibit, label: t('inspector.cert.revokeAction'), danger: true }] : []),
    ...others.filter((a) => !a.danger && a.id !== 'revoke').sort((a, b) => menuRank(a.id) - menuRank(b.id)),
    {
      id: 'favorite', icon: Star,
      label: favorite ? t('inspector.cert.unfavorite') : t('inspector.cert.favorite'),
      onClick: () => toggleFavorite({ id: cert.id, name: title, subtitle: cert.issuer ? extractCN(cert.issuer) : '' }),
    },
    ...(trust.offered ? [{ id: 'trust', icon: ShieldCheck, label: t('details.addIssuerToTrustStore'), onClick: trust.add }] : []),
    ...others.filter((a) => a.danger && a.id !== 'revoke'),
  ]
  const sections = INSPECTOR_TYPES.certificate.sections

  return (
    <>
      <header className="ins-heading">
        <div className="ins-title">
          <Certificate className="ins-title-icon" aria-hidden="true" />
          <h2>{title}</h2>
          <StatusPill {...certificateState(cert, t)} />
        </div>
        <div className="ins-actions">
          {exportAction && (
            <button type="button" className={cn('lv-btn', !renewAction && 'is-primary')} data-write="false" onClick={exportAction.onClick}>
              <DownloadSimple size={17} aria-hidden="true" />{exportAction.label}
            </button>
          )}
          {renewAction && (
            <button type="button" className="lv-btn is-primary" onClick={renewAction.onClick}>
              <RefreshIcon size={17} />{renewAction.label}
            </button>
          )}
          <MoreActionsMenu items={menu} label={t('inspector.moreActions', { name: title })}
            title={t('inspector.cert.actionsTitle')} name={title} />
        </div>
      </header>
      <SectionTabs objectKey={objectKey} sections={sections} current={section} onSelect={onSection}
        labelOf={(s) => t(`inspector.sections.${s}`)} />
      <div role="tabpanel" id={`${panelId(objectKey)}-section`} aria-labelledby={`${tabId(objectKey)}-${section}`}
        className="ins-panel" tabIndex={0}>
        {section === 'overview' && (
          <CertificateOverview cert={cert} title={title} columns={columns} openCa={openCa} onOpenRelated={onOpenRelated} />
        )}
        {section === 'chain' && <CertificateChain cert={cert} title={title} columns={columns} openCa={openCa} onChanged={onChanged} />}
        {section === 'extensions' && <CertificateExtensionList cert={cert} columns={columns} />}
        {section === 'history' && <CertificateHistory cert={cert} />}
        {section === 'pem' && <CertificatePem cert={cert} />}
      </div>
    </>
  )
}
