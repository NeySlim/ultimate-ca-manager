/**
 * Certificate in the inspector, after the Atelier detail: heading (icon, name,
 * state, Export, Renew when it applies, « ⋯ » for the other actions), then the
 * Overview, Chain, Extensions, History and PEM sections.
 */
import { useTranslation } from 'react-i18next'
import { Certificate, DownloadSimple, ArrowsClockwise, Star } from '@phosphor-icons/react'
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
const BUTTONS = ['export', 'renew']

export function CertificateDetail({ cert, objectKey, title, actions, section, onSection, onChanged, onOpenRelated, onOpenCa }) {
  const { t } = useTranslation()
  const placement = useDockPlacementContext()
  const columns = placement === 'bottom' ? 3 : 1
  const { isFavorite, toggleFavorite } = useFavorites('certificates')
  const openCa = useOpenCa(cert, onOpenCa)

  const visible = actions.filter((a) => a.visible && a.inBar !== false)
  const exportAction = visible.find((a) => a.id === 'export')
  const renewAction = visible.find((a) => a.id === 'renew')
  const favorite = isFavorite(cert.id)
  const others = visible.filter((a) => !BUTTONS.includes(a.id))
  const menu = [
    ...others.filter((a) => !a.danger),
    {
      id: 'favorite', icon: Star,
      label: favorite ? t('inspector.cert.unfavorite') : t('inspector.cert.favorite'),
      onClick: () => toggleFavorite({ id: cert.id, name: title, subtitle: cert.issuer ? extractCN(cert.issuer) : '' }),
    },
    ...others.filter((a) => a.danger).map((a, i) => ({ ...a, separatorBefore: i === 0 })),
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
            <button type="button" className={cn('lv-btn', !renewAction && 'is-primary')} onClick={exportAction.onClick}>
              <DownloadSimple size={15} aria-hidden="true" />{exportAction.label}
            </button>
          )}
          {renewAction && (
            <button type="button" className="lv-btn is-primary" onClick={renewAction.onClick}>
              <ArrowsClockwise size={15} aria-hidden="true" />{renewAction.label}
            </button>
          )}
          <MoreActionsMenu items={menu} label={t('inspector.moreActions', { name: title })} />
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
