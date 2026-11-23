/**
 * Domains of the built-in ACME server (the CA and the approval of their orders), drawn as the
 * mockup's module list with its dock; edit and delete stay on the row and in the dock.
 */
import { useTranslation } from 'react-i18next'
import { Btn, ListView, Dock, DockBody, Section, Facts, EmptyBlock, Pill, useClientList, useSortParam } from '../../components/atelier'
import { useDockId } from '../../components/atelier/useDockParam'
import { SlotDock } from '../protocols/dockSlot'

const BY_DOMAIN = { key: 'name', asc: true }
const SORT_KEYS = ['name', 'ca', 'state']

export default function LocalDomainsTab({ localDomains, onAdd, onEdit, onDelete, canWrite, canDelete }) {
  const { t } = useTranslation()
  // The open object lives in the URL (`item`)
  const { openId, setOpenId } = useDockId()
  const open = localDomains.find((d) => d.id === openId)
  const approval = (d) => <Pill label={t(d.auto_approve ? 'common.auto' : 'common.manual')} tone={d.auto_approve ? 'good' : 'warn'} icon={d.auto_approve ? 'check' : 'clock'} />
  const actions = (d) => [
    ...(canWrite ? [{ icon: 'settings', label: t('common.edit'), onClick: () => onEdit(d), write: true }] : []),
    ...(canDelete ? [{ icon: 'close', label: t('common.delete'), onClick: () => onDelete(d), write: true }] : []),
  ]
  // The API sends every domain: sorted and paged here, the sort kept in the address
  const sortParam = useSortParam(BY_DOMAIN, SORT_KEYS)
  const list = useClientList(localDomains, {
    sortParam,
    sorts: { name: (d) => d.domain, ca: (d) => d.issuing_ca_name || t('acme.defaultCA'), state: (d) => (d.auto_approve ? 0 : 1) },
  })
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
            <Facts items={[
              [t('acme.domain'), open.domain],
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
      <ListView label={t('acme.localDomains')} caption={t('acme.domainsCaption')} icon="globe" list={list} nameSort="name"
        title={(d) => d.domain} status={approval} openedId={openId} onOpen={(d) => setOpenId(d.id)}
        columns={[{ id: 'ca', label: t('acme.issuingCA'), cell: (d) => d.issuing_ca_name || t('acme.defaultCA'), kind: 'text', priority: 2, sort: 'ca' }, { status: true, sort: 'state' }]}
        rowActions={actions}
        empty={<EmptyBlock id="acme-local-domains" icon="globe" title={t('acme.noLocalDomains')} text={t('acme.noLocalDomainsDesc')}
          action={canWrite ? { label: t('acme.addDomain'), icon: 'plus', onClick: onAdd, primary: true } : undefined} />}
        footer={{ range: list.paged ? t('table.range', { start: list.start, end: list.end, total: list.total }) : t('acme.domainsRange', { count: list.total }) }} />
      <SlotDock>{dock}</SlotDock>
    </>
  )
}
