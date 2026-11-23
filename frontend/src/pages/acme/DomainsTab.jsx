/**
 * Domains of the ACME client (DNS-01 through a provider), drawn as the mockup's module list with its
 * dock: provider, issuing CA, wildcard and approval per domain; test, edit and delete stay on the
 * row and in the dock, each behind its right.
 */
import { useTranslation } from 'react-i18next'
import { Btn, ListView, Dock, DockBody, Section, Facts, EmptyBlock, Pill, useClientList, useSortParam } from '../../components/atelier'
import { useDockId } from '../../components/atelier/useDockParam'
import { SlotDock } from '../protocols/dockSlot'
import { factRow, yesNoState } from '../protocols/factRows'

const BY_DOMAIN = { key: 'name', asc: true }
const SORT_KEYS = ['name', 'provider', 'ca', 'wildcard', 'state']

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
  // The API sends every domain: sorted and paged here, the sort kept in the address
  const sortParam = useSortParam(BY_DOMAIN, SORT_KEYS)
  const list = useClientList(acmeDomains, {
    sortParam,
    sorts: {
      name: (d) => d.domain, provider: (d) => d.dns_provider_name || d.dns_provider_type, ca: (d) => d.issuing_ca_name || t('acme.defaultCA'),
      wildcard: (d) => (d.is_wildcard_allowed ? 0 : 1), state: (d) => (d.auto_approve ? 0 : 1),
    },
  })
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
            <Facts items={[
              [t('acme.domain'), open.domain],
              factRow(t('acme.provider'), open.dns_provider_name || open.dns_provider_type),
              [t('acme.issuingCA'), open.issuing_ca_name || t('acme.defaultCA')],
              { label: t('acme.wildcard'), state: yesNoState(t, open.is_wildcard_allowed) },
              [t('acme.autoApprove'), approval(open)],
            ]} />
          </Section>
        </div>
      </DockBody>
    </Dock>
  )
  return (
    <>
      <ListView label={t('acme.domains')} caption={t('acme.domainsCaption')} icon="globe" list={list} nameSort="name"
        title={(d) => d.domain} status={approval} openedId={openId} onOpen={(d) => setOpenId(d.id)}
        columns={[
          { id: 'provider', label: t('acme.provider'), cell: (d) => d.dns_provider_name || d.dns_provider_type || '—', kind: 'text', priority: 2, sort: 'provider' },
          { id: 'ca', label: t('acme.issuingCA'), cell: (d) => d.issuing_ca_name || t('acme.defaultCA'), kind: 'text', priority: 3, sort: 'ca' },
          { id: 'wildcard', label: t('acme.columns.wildcard'), labelFull: t('acme.wildcard'), cell: (d) => t(d.is_wildcard_allowed ? 'common.yes' : 'common.no'),
            kind: 'fit', priority: 3, labelled: true, sort: 'wildcard' },
          { status: true, sort: 'state' },
        ]}
        rowActions={actions}
        empty={<EmptyBlock id="acme-domains" icon="globe" title={t('acme.noDomainsYet')} text={t('acme.noDomainsDesc')}
          action={canWrite ? { label: t('acme.addDomain'), icon: 'plus', onClick: onAdd, primary: true } : undefined} />}
        footer={{ range: list.paged ? t('table.range', { start: list.start, end: list.end, total: list.total }) : t('acme.domainsRange', { count: list.total }) }} />
      <SlotDock>{dock}</SlotDock>
    </>
  )
}
