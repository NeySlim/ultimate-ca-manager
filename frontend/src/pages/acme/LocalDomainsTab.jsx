/**
 * Domains of the built-in ACME server (the CA and the approval of their orders), drawn as the
 * mockup's module list with its dock; edit and delete stay on the row and in the dock.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Btn, ListView, Dock, DockBody, Section, Props, EmptyBlock, Pill } from '../../components/atelier'
import { SlotDock } from '../protocols/dockSlot'

export default function LocalDomainsTab({ localDomains, onAdd, onEdit, onDelete, canWrite, canDelete }) {
  const { t } = useTranslation()
  const [openId, setOpenId] = useState(null)
  const open = localDomains.find((d) => d.id === openId)
  const approval = (d) => <Pill label={t(d.auto_approve ? 'common.auto' : 'common.manual')} tone={d.auto_approve ? 'good' : 'warn'} icon={d.auto_approve ? 'check' : 'clock'} />
  const actions = (d) => [
    ...(canWrite ? [{ icon: 'settings', label: t('common.edit'), onClick: () => onEdit(d), write: true }] : []),
    ...(canDelete ? [{ icon: 'close', label: t('common.delete'), onClick: () => onDelete(d), write: true }] : []),
  ]
  const dock = open && (
    <Dock label={t('atelier.detailOf', { name: t('acme.localDomains') })} tabsLabel={t('atelier.openItem')} activeKey={open.id}
      tabs={[{ key: open.id, title: open.domain, icon: 'globe' }]} onClose={() => setOpenId(null)}>
      <DockBody icon="globe" title={open.domain} badge={approval(open)} section="domain" onSection={() => {}}
        sectionsLabel={t('atelier.sectionsOf', { name: open.domain })} sections={[['domain', t('atelier.overview')]]}
        actions={<>
          {canWrite && <Btn icon="settings" write onClick={() => onEdit(open)}>{t('common.edit')}</Btn>}
          {canDelete && <Btn icon="close" write onClick={() => { onDelete(open); setOpenId(null) }}>{t('common.delete')}</Btn>}
        </>}>
        <div className="module-detail">
          <Section title={t('atelier.properties')}>
            <Props items={[
              [t('acme.domain'), <span key="d" className="mono">{open.domain}</span>],
              [t('acme.issuingCA'), open.issuing_ca_name || t('acme.defaultCA')],
              [t('acme.autoApprove'), approval(open)],
            ]} />
          </Section>
        </div>
      </DockBody>
    </Dock>
  )
  return (
    <>
      <ListView label={t('acme.localDomains')} caption={t('acme.domainsCaption')} icon="globe" rows={localDomains}
        title={(d) => d.domain} status={approval} openedId={openId} onOpen={(d) => setOpenId(d.id)}
        columns={[{ id: 'ca', label: t('acme.issuingCA'), cell: (d) => d.issuing_ca_name || t('acme.defaultCA'), grow: true }, { status: true }]}
        rowActions={actions}
        empty={<EmptyBlock id="acme-local-domains" icon="globe" title={t('acme.noLocalDomains')} text={t('acme.noLocalDomainsDesc')}
          action={canWrite ? { label: t('acme.addDomain'), icon: 'plus', onClick: onAdd, primary: true } : undefined} />}
        footer={{ range: t('acme.domainsRange', { count: localDomains.length }) }} />
      <SlotDock>{dock}</SlotDock>
    </>
  )
}
