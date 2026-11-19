/**
 * CertificateDetail: one certificate in the inspector. Heading (name, state, Export, the
 * main action, a menu for the rest), then Overview, Chain, Extensions, History and PEM.
 * The actions come from hooks/useEntityActions; what a permission hides is not drawn.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { Certificate, DownloadSimple, ArrowsClockwise, DotsThree, Star } from '@phosphor-icons/react'
import { StatusPill } from '../../list/StatusPill'
import { certificateState } from '../../../lib/certificateState'
import { extractCN, cn } from '../../../lib/utils'
import { useFavorites, usePermission } from '../../../hooks'
import { useNotification } from '../../../contexts'
import { certificatesService, casService, truststoreService } from '../../../services'
import { INSPECTOR_TYPES } from '../config'
import { SectionTabs, tabId, panelId } from '../InspectorTabs'
import { CertificateOverview } from './CertificateOverview'
import { CertificateChain } from './CertificateChain'
import { CertificateExtensionsList } from './CertificateExtensionsList'
import { CertificateHistory } from './CertificateHistory'
import { CertificatePem } from './CertificatePem'

const CERTIFICATE_SECTIONS = INSPECTOR_TYPES.certificate.sections
// Drawn as buttons of the heading; every other visible action goes to the menu
const HEAD_ACTIONS = ['export', 'renew']

export function CertificateDetail({ objectKey, certificate, title, actions = [], layout = 'columns', onChanged, onOpen }) {
  const { t } = useTranslation()
  const [section, setSection] = useState('overview')
  const { isFavorite, toggleFavorite } = useFavorites('certificates')
  const { canRead, canWrite } = usePermission()
  const { showSuccess, showError } = useNotification()
  const cert = certificate

  const shown = actions.filter((a) => a.visible)
  const exportAction = shown.find((a) => a.id === 'export')
  const renew = shown.find((a) => a.id === 'renew')
  const rest = shown.filter((a) => !HEAD_ACTIONS.includes(a.id))
  const plain = rest.filter((a) => !a.danger)
  const danger = rest.filter((a) => a.danger)
  const favorite = isFavorite(cert.id)

  // The issuing authority is named by its reference: its id comes from the list of authorities
  const openIssuer = cert.caref && canRead('cas') && onOpen ? async () => {
    try {
      const res = await casService.getAll()
      const ca = (res?.data || []).find((c) => c.refid === cert.caref)
      if (ca) onOpen('ca', ca.id)
    } catch (err) {
      showError(err?.message || t('inspector.loadFailed'))
    }
  } : undefined

  const addIssuerToTrustStore = cert.caref && canWrite('truststore') ? async () => {
    try {
      await truststoreService.addFromCA(cert.caref)
      showSuccess(t('details.addedToTrustStore'))
      const res = await certificatesService.getById(cert.id)
      if (res?.data) onChanged?.(res.data)
    } catch (err) {
      showError(err?.message || t('details.addToTrustStoreFailed'))
    }
  } : undefined

  const item = (a) => {
    const Icon = a.icon
    return (
      <DropdownMenu.Item key={a.id} className={cn('insp-pop-item', a.danger && 'is-danger')} disabled={a.disabled} onSelect={() => a.onClick?.()}>
        {Icon && <Icon aria-hidden="true" />}
        {a.label}
      </DropdownMenu.Item>
    )
  }

  return (
    <>
      <header className="insp-heading">
        <div className="insp-title">
          <Certificate aria-hidden="true" />
          <h2>{title}</h2>
          <StatusPill {...certificateState(cert, t)} />
        </div>
        <div className="insp-actions">
          {exportAction && (
            <button type="button" className={cn('insp-btn', !renew && 'is-primary')} onClick={exportAction.onClick} disabled={exportAction.disabled}>
              <DownloadSimple aria-hidden="true" />{exportAction.label}
            </button>
          )}
          {renew && (
            <button type="button" className="insp-btn is-primary" onClick={renew.onClick} disabled={renew.disabled}>
              <ArrowsClockwise aria-hidden="true" />{renew.label}
            </button>
          )}
          <DropdownMenu.Root>
            <DropdownMenu.Trigger asChild>
              <button type="button" className="insp-btn is-icon" aria-label={t('inspector.moreActions', { name: title })} title={t('inspector.moreActionsShort')}>
                <DotsThree weight="bold" aria-hidden="true" />
              </button>
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content className="insp-pop" align="end" sideOffset={4}>
                {plain.map(item)}
                <DropdownMenu.Item className="insp-pop-item" onSelect={() => toggleFavorite({
                  id: cert.id, name: title, subtitle: cert.issuer ? extractCN(cert.issuer) : '',
                })}>
                  <Star weight={favorite ? 'fill' : 'regular'} aria-hidden="true" />
                  {t(favorite ? 'inspector.unfavorite' : 'inspector.favorite')}
                </DropdownMenu.Item>
                {danger.length > 0 && <DropdownMenu.Separator className="insp-pop-sep" />}
                {danger.map(item)}
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu.Root>
        </div>
      </header>
      <SectionTabs objectKey={objectKey} sections={CERTIFICATE_SECTIONS} current={section} onSelect={setSection} />
      <div role="tabpanel" id={`${panelId(objectKey)}-section`} aria-labelledby={`${tabId(objectKey)}-${section}`}
        tabIndex={0} className="insp-panel" data-layout={layout}>
        {section === 'overview' && (
          <CertificateOverview certificate={cert} layout={layout} onShowExtensions={() => setSection('extensions')}
            onOpenIssuer={openIssuer} onOpenRelated={onOpen ? (id) => onOpen('certificate', id) : undefined} />
        )}
        {section === 'chain' && (
          <CertificateChain certificate={cert} onOpenIssuer={openIssuer} onAddToTrustStore={addIssuerToTrustStore} />
        )}
        {section === 'extensions' && <CertificateExtensionsList certificate={cert} />}
        {section === 'history' && <CertificateHistory certificate={cert} />}
        {section === 'pem' && <CertificatePem certificate={cert} />}
      </div>
    </>
  )
}
