/**
 * Domains of the ACME client (DNS-01 through a provider), drawn as the mockup's module list with its
 * dock: provider, issuing CA, wildcard and approval per domain; test, edit and delete stay on the
 * row and in the dock, each behind its right.
 */
import { useTranslation } from 'react-i18next'
import { Btn, ListView, Dock, DockBody, Section, Props, EmptyBlock, Pill } from '../../components/atelier'
import { useDockId } from '../../components/atelier/useDockParam'
import { SlotDock } from '../protocols/dockSlot'
import { YesNo } from '../protocols/atelierParts'

export default function DomainsTab({ acmeDomains, onAdd, onEdit, onDelete, onTest, canWrite, canDelete }) {
  const { t } = useTranslation()
  // The open object lives in the URL (`item`)
  const { openId, setOpenId } = useDockId()
  const open = acmeDomains.find((d) => d.id === openId)
  const approval = (d) => <Pill label={t(d.auto_approve ? 'common.auto' : 'common.manual')} tone={d.auto_approve ? 'good' : 'warn'} icon={d.auto_approve ? 'check' : 'clock'} />
  const actions = (d) => [
    { icon: 'send', label: t('acme.testDnsAccess'), onClick: () => onTest(d) },
    ...(canWrite ? [{ icon: 'settings', label: t('common.edit'), onClick: () => onEdit(d), write: true }] : []),
    ...(canDelete ? [{ icon: 'close', label: t('common.delete'), onClick: () => onDelete(d), write: true }] : []),
  ]
  const dock = open && (
    <Dock label={t('atelier.detailOf', { name: t('acme.domains') })} tabsLabel={t('atelier.openItem')} activeKey={open.id}
      tabs={[{ key: open.id, title: open.domain, icon: 'globe' }]} onClose={() => setOpenId(null)}>
      <DockBody icon="globe" title={open.domain} badge={approval(open)} section="domain" onSection={() => {}}
        sectionsLabel={t('atelier.sectionsOf', { name: open.domain })} sections={[['domain', t('atelier.overview')]]}
        actions={<>
          <Btn icon="send" onClick={() => onTest(open)}>{t('acme.testDnsAccess')}</Btn>
          {canWrite && <Btn icon="settings" write onClick={() => onEdit(open)}>{t('common.edit')}</Btn>}
          {canDelete && <Btn icon="close" write onClick={() => { onDelete(open); setOpenId(null) }}>{t('common.delete')}</Btn>}
        </>}>
        <div className="module-detail">
          <Section title={t('atelier.properties')}>
            <Props items={[
              [t('acme.domain'), <span key="d" className="mono">{open.domain}</span>],
              [t('acme.provider'), open.dns_provider_name || open.dns_provider_type || '—'],
              [t('acme.issuingCA'), open.issuing_ca_name || t('acme.defaultCA')],
              [t('acme.wildcard'), <YesNo key="w" value={open.is_wildcard_allowed} />],
              [t('acme.autoApprove'), approval(open)],
            ]} />
          </Section>
        </div>
      </DockBody>
    </Dock>
  )
  return (
    <>
      <ListView label={t('acme.domains')} caption={t('acme.domainsCaption')} icon="globe" rows={acmeDomains}
        title={(d) => d.domain} status={approval} openedId={openId} onOpen={(d) => setOpenId(d.id)}
        columns={[
          { id: 'provider', label: t('acme.provider'), cell: (d) => d.dns_provider_name || d.dns_provider_type || '—', grow: true },
          { id: 'ca', label: t('acme.issuingCA'), cell: (d) => d.issuing_ca_name || t('acme.defaultCA') },
          { id: 'wildcard', label: t('acme.wildcard'), cell: (d) => t(d.is_wildcard_allowed ? 'common.yes' : 'common.no') },
          { status: true },
        ]}
        rowActions={actions}
        empty={<EmptyBlock id="acme-domains" icon="globe" title={t('acme.noDomainsYet')} text={t('acme.noDomainsDesc')}
          action={canWrite ? { label: t('acme.addDomain'), icon: 'plus', onClick: onAdd, primary: true } : undefined} />}
        footer={{ range: t('acme.domainsRange', { count: acmeDomains.length }) }} />
      <SlotDock>{dock}</SlotDock>
    </>
  )
}
