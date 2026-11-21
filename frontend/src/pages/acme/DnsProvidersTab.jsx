/**
 * DNS providers of the ACME client (DNS-01), drawn as the mockup's module list with its dock: type
 * and default per provider; test, edit and delete stay on the row and in the dock.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Btn, ListView, Dock, DockBody, Section, Props, EmptyBlock, Pill } from '../../components/atelier'
import { SlotDock } from '../protocols/dockSlot'
import { Notice } from '../protocols/atelierParts'

export default function DnsProvidersTab({ dnsProviders, onAddProvider, onEditProvider, onTestProvider, onDeleteProvider, canWrite, canDelete }) {
  const { t } = useTranslation()
  const [openId, setOpenId] = useState(null)
  const open = dnsProviders.find((p) => p.id === openId)
  const state = (p) => (p.enabled === false
    ? <Pill label={t('common.disabled')} tone="muted" />
    : <Pill label={p.is_default ? t('common.default') : t('common.active')} tone="good" />)
  const actions = (p) => [
    { icon: 'send', label: t('common.test'), onClick: () => onTestProvider(p) },
    ...(canWrite ? [{ icon: 'settings', label: t('common.edit'), onClick: () => onEditProvider(p), write: true }] : []),
    ...(canDelete ? [{ icon: 'close', label: t('common.delete'), onClick: () => onDeleteProvider(p), write: true }] : []),
  ]
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
      <ListView label={t('acme.dnsProviders')} caption={t('acme.providersCaption')} icon="server" rows={dnsProviders}
        title={(p) => p.name} status={state} openedId={openId} onOpen={(p) => setOpenId(p.id)}
        columns={[{ id: 'type', label: t('common.providerType'), cell: (p) => p.provider_type, grow: true }, { status: true }]}
        rowActions={actions}
        empty={<EmptyBlock id="acme-dns" icon="server" title={t('acme.noDnsProviders')} text={t('acme.noDnsProvidersDesc')}
          action={canWrite ? { label: t('common.addDnsProvider'), icon: 'plus', onClick: onAddProvider, primary: true } : undefined} />}
        footer={{ range: t('acme.providersRange', { count: dnsProviders.length }) }} />
      <SlotDock>{dock}</SlotDock>
    </>
  )
}
