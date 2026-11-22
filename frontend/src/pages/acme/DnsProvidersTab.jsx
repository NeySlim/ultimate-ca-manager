/**
 * DNS providers of the ACME client (DNS-01), drawn as the mockup's module list with its dock: type
 * and default per provider; test, edit and delete stay on the row and in the dock.
 */
import { useTranslation } from 'react-i18next'
import { Btn, ListView, Dock, DockBody, Section, Props, EmptyBlock, Pill, useClientList, useSortParam } from '../../components/atelier'
import { useDockId } from '../../components/atelier/useDockParam'
import { SlotDock } from '../protocols/dockSlot'
import { Notice } from '../protocols/atelierParts'

const BY_NAME = { key: 'name', asc: true }
const SORT_KEYS = ['name', 'type', 'state']
// Disabled last, the default first among the active (the pill's three words)
const stateRank = (p) => (p.enabled === false ? 2 : p.is_default ? 0 : 1)

export default function DnsProvidersTab({ dnsProviders, onAddProvider, onEditProvider, onTestProvider, onDeleteProvider, canWrite, canDelete }) {
  const { t } = useTranslation()
  // The open object lives in the URL (`item`)
  const { openId, setOpenId } = useDockId()
  const open = dnsProviders.find((p) => p.id === openId)
  const state = (p) => (p.enabled === false
    ? <Pill label={t('common.disabled')} tone="muted" />
    : <Pill label={p.is_default ? t('common.default') : t('common.active')} tone="good" />)
  const actions = (p) => [
    { icon: 'send', label: t('common.test'), onClick: () => onTestProvider(p) },
    ...(canWrite ? [{ icon: 'settings', label: t('common.edit'), onClick: () => onEditProvider(p), write: true }] : []),
    ...(canDelete ? [{ icon: 'close', label: t('common.delete'), onClick: () => onDeleteProvider(p), write: true }] : []),
  ]
  // The API sends every provider: sorted and paged here, the sort kept in the address
  const sortParam = useSortParam(BY_NAME, SORT_KEYS)
  const list = useClientList(dnsProviders, { sortParam, sorts: { name: (p) => p.name, type: (p) => p.provider_type, state: stateRank } })
  const dock = open && (
    <Dock label={t('atelier.detailOf', { name: t('acme.dnsProviders') })} tabsLabel={t('atelier.openItem')} activeKey={open.id}
      tabs={[{ key: open.id, title: open.name, icon: 'server' }]} onClose={() => setOpenId(null)}>
      <DockBody icon="server" title={open.name} badge={state(open)} section="provider" onSection={() => {}}
        sectionsLabel={t('atelier.sectionsOf', { name: open.name })} sections={[['provider', t('atelier.overview')]]}
        actions={<>
          <Btn icon="send" onClick={() => onTestProvider(open)}>{t('common.test')}</Btn>
          {canWrite && <Btn icon="settings" write onClick={() => onEditProvider(open)}>{t('common.edit')}</Btn>}
          {canDelete && <Btn icon="close" write onClick={() => { onDeleteProvider(open); setOpenId(null) }}>{t('common.delete')}</Btn>}
        </>}>
        <div className="module-detail">
          <Section title={t('atelier.properties')}>
            <Props items={[
              [t('common.providerType'), open.provider_type],
              [t('common.default'), t(open.is_default ? 'common.yes' : 'common.no')],
              [t('acme.credentials'), (open.credential_keys || []).join(', ') || '—'],
            ]} />
            <Notice>{t('acme.dnsProvidersAboutDesc')}</Notice>
          </Section>
        </div>
      </DockBody>
    </Dock>
  )
  return (
    <>
      <ListView label={t('acme.dnsProviders')} caption={t('acme.providersCaption')} icon="server" list={list} nameSort="name"
        title={(p) => p.name} status={state} openedId={openId} onOpen={(p) => setOpenId(p.id)}
        columns={[{ id: 'type', label: t('common.type'), labelFull: t('common.providerType'), cell: (p) => p.provider_type, kind: 'fit', priority: 3, sort: 'type' }, { status: true, sort: 'state' }]}
        rowActions={actions}
        empty={<EmptyBlock id="acme-dns" icon="server" title={t('acme.noDnsProviders')} text={t('acme.noDnsProvidersDesc')}
          action={canWrite ? { label: t('common.addDnsProvider'), icon: 'plus', onClick: onAddProvider, primary: true } : undefined} />}
        footer={{ range: list.paged ? t('table.range', { start: list.start, end: list.end, total: list.total }) : t('acme.providersRange', { count: list.total }) }} />
      <SlotDock>{dock}</SlotDock>
    </>
  )
}
