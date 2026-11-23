import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Input, SecretInput, Select, Textarea, ToggleSwitch, Modal } from '../../components/atelier/Form'
import { Btn, Pill, ListView, Dock, DockBody, Section, Facts, EmptyBlock, useClientList, useSortParam } from '../../components/atelier'
import { useDockId } from '../../components/atelier/useDockParam'
import { SlotDock } from '../protocols/dockSlot'
import { copyRow, fact } from '../../components/atelier/facts'
import DnsUpdateKeysPanel from './DnsUpdateKeysPanel'

const EMPTY_FORM = {
  label: '',
  directory_url: '',
  email: '',
  account_key_algorithm: 'ES256',
  account_key_pem: '',
  eab_kid: '',
  eab_hmac_key: '',
  is_default: false,
  proxy_enabled: false,
  proxy_slug: '',
  order_poll_timeout_sec: '180',
  order_poll_interval_sec: '3',
  http_timeout_sec: '60',
  preferred_chain: '',
}

// The proxy answers only when it is enabled and has a slug.
const proxyIsOn = (acct) => !!(acct.proxy_enabled && acct.proxy_slug)

const BY_NAME = { key: 'name', asc: true }
const SORT_KEYS = ['name', 'directory', 'email', 'default', 'proxy', 'state']

/**
 * Multi-CA account manager for the ACME client. Lists every external ACME
 * authority (Let's Encrypt, ZeroSSL...) UCM can request certificates
 * from, and lets admins add/edit/remove them, set the default, and register.
 */
export default function CaAccountsManager({
  accounts = [],
  proxyPublicBase = '',
  dnsUpdatePort = 0,
  canWrite,
  canDelete,
  onCreate,
  onUpdate,
  onDelete,
  onDeactivate,
  onSetDefault,
  onRegister,
  createSignal = 0,
}) {
  const { t } = useTranslation()
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [busy, setBusy] = useState(false)
  // The open account and its section live in the URL (`item`, `section`)
  const { openId, setOpenId, section, setSection } = useDockId({ sections: ['overview', 'dnsupdate'] })

  const openCreate = () => {
    setEditingId(null)
    setForm(EMPTY_FORM)
    setShowForm(true)
  }

  // The server keeps one default: it is moved by choosing another account, never unticked
  const isEditingDefault = Boolean(editingId) && accounts.some(a => a.id === editingId && a.is_default)

  const openEdit = (acct) => {
    setEditingId(acct.id)
    setForm({
      label: acct.label || '',
      directory_url: acct.directory_url || '',
      email: acct.email || '',
      account_key_algorithm: acct.account_key_algorithm || 'ES256',
      eab_kid: acct.eab_kid || '',
      eab_hmac_key: '',
      is_default: !!acct.is_default,
      proxy_enabled: !!acct.proxy_enabled,
      proxy_slug: acct.proxy_slug || '',
      order_poll_timeout_sec: String(acct.order_poll_timeout_sec ?? 180),
      order_poll_interval_sec: String(acct.order_poll_interval_sec ?? 3),
      http_timeout_sec: String(acct.http_timeout_sec ?? 60),
      preferred_chain: acct.preferred_chain || '',
    })
    setShowForm(true)
  }

  const closeForm = () => {
    setShowForm(false)
    setEditingId(null)
    setForm(EMPTY_FORM)
  }

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    try {
      const timing = {
        order_poll_timeout_sec: parseInt(form.order_poll_timeout_sec, 10),
        order_poll_interval_sec: parseInt(form.order_poll_interval_sec, 10),
        http_timeout_sec: parseInt(form.http_timeout_sec, 10),
      }
      if (editingId) {
        const payload = {
          label: form.label,
          email: form.email,
          eab_kid: form.eab_kid,
          is_default: form.is_default,
          proxy_enabled: form.proxy_enabled,
          proxy_slug: form.proxy_slug,
          preferred_chain: form.preferred_chain,
          ...timing,
        }
        if (form.eab_hmac_key) payload.eab_hmac_key = form.eab_hmac_key
        await onUpdate(editingId, payload)
      } else {
        const payload = { ...form, ...timing }
        if (!payload.account_key_pem) delete payload.account_key_pem
        await onCreate(payload)
      }
      closeForm()
    } finally {
      setBusy(false)
    }
  }

  // The page head's Ajouter une AC opens the form
  useEffect(() => { if (createSignal) openCreate() }, [createSignal])

  const open = accounts.find((a) => a.id === openId)
  // The API sends every upstream CA: sorted and paged here, the sort kept in the address
  const sortParam = useSortParam(BY_NAME, SORT_KEYS)
  const list = useClientList(accounts, {
    sortParam,
    sorts: {
      name: (a) => a.label, directory: (a) => a.directory_url, email: (a) => a.email || null, default: (a) => (a.is_default ? 0 : 1),
      proxy: (a) => (proxyIsOn(a) ? a.proxy_slug : null), state: (a) => (a.is_registered ? 0 : 1),
    },
  })
  const pill = (a) => <Pill label={t(a.is_registered ? 'acme.registered' : 'acme.notRegistered')} tone={a.is_registered ? 'good' : 'warn'} />
  const proxyUrl = (a) => `${proxyPublicBase || '/acme/proxy'}/${a.proxy_slug}/directory`
  const sections = [['overview', t('atelier.overview')], ...(proxyIsOn(open || {}) || open?.dns_update_key_count > 0 ? [['dnsupdate', t('acme.dnsUpdate.title')]] : [])]
  const shown = sections.some(([id]) => id === section) ? section : 'overview'

  const dock = open && (
    <Dock label={t('atelier.detailOf', { name: t('acme.certificateAuthorities') })} tabsLabel={t('atelier.openItem')} activeKey={open.id}
      tabs={[{ key: open.id, title: open.label, icon: 'server' }]} onClose={() => setOpenId(null)}>
      <DockBody icon="server" title={open.label} badge={pill(open)} section={shown} onSection={setSection}
        sectionsLabel={t('atelier.sectionsOf', { name: open.label })} sections={sections}
        actions={canWrite && <>
          {!open.is_registered && <Btn icon="key" write onClick={() => onRegister(open.id, open.email)}>{t('acme.registerAccount')}</Btn>}
          {!open.is_default && <Btn icon="check" write onClick={() => onSetDefault(open.id)}>{t('acme.setDefault')}</Btn>}
          <Btn icon="settings" write onClick={() => openEdit(open)}>{t('common.edit')}</Btn>
          {canDelete && open.is_registered && onDeactivate && <Btn tone="danger" icon="block" onClick={() => onDeactivate(open.id)}>{t('common.deactivate')}</Btn>}
          {canDelete && <Btn icon="close" onClick={() => onDelete(open.id)}>{t('common.delete')}</Btn>}
        </>}>
        {shown === 'overview' && (
          <div className="module-detail">
            <Section title={t('atelier.properties')}>
              <Facts items={[
                copyRow(t('acme.directoryUrl'), open.directory_url, 'url'),
                fact(t('acme.contactEmail'), open.email),
                fact(t('acme.accountKeyType'), open.account_key_algorithm),
                [t('common.default'), t(open.is_default ? 'common.yes' : 'common.no')],
                open.eab_kid ? copyRow('EAB', open.eab_kid, undefined, { long: true }) : { label: 'EAB', absent: t('common.no') },
                open.environment && open.environment !== 'custom' && [t('acme.environment'), open.environment],
                open.account_url && copyRow(t('acme.accountUrl'), open.account_url, 'url'),
              ]} />
            </Section>
            <Section title={t('acme.caTimingSettings')}>
              <Facts items={[
                [t('acme.caOrderPollTimeout'), String(open.order_poll_timeout_sec ?? 180)],
                [t('acme.caOrderPollInterval'), String(open.order_poll_interval_sec ?? 3)],
                [t('acme.caHttpTimeout'), String(open.http_timeout_sec ?? 60)],
                open.preferred_chain && [t('acme.preferredChain'), open.preferred_chain],
                proxyIsOn(open) && copyRow(t('acme.proxySlug'), proxyUrl(open), 'url'),
              ]} />
            </Section>
          </div>
        )}
        {shown === 'dnsupdate' && (
          <div className="module-detail">
            <DnsUpdateKeysPanel account={open} proxyPublicBase={proxyPublicBase} dnsUpdatePort={dnsUpdatePort}
              proxyActive={proxyIsOn(open)} canWrite={canWrite} canDelete={canDelete} />
          </div>
        )}
      </DockBody>
    </Dock>
  )

  return (
    <>
      <ListView label={t('acme.certificateAuthorities')} caption={t('acme.upstreamCaption')} icon="server" list={list} nameSort="name"
        title={(a) => a.label} status={pill} openedId={openId} onOpen={(a) => { if (a.id !== openId) setSection('overview'); setOpenId(a.id) }}
        columns={[
          // The directory takes the room left and gives it back first, its whole URL in its title
          { id: 'directory', label: t('acme.directoryUrl'), cell: (a) => <span className="mono">{a.directory_url}</span>, grow: true, muted: true,
            kind: 'text', priority: 3, title: (a) => a.directory_url || undefined, sort: 'directory' },
          { id: 'email', label: t('acme.contactEmail'), cell: (a) => a.email || '—', kind: 'text', priority: 4, sort: 'email' },
          { id: 'default', label: t('common.default'), cell: (a) => t(a.is_default ? 'common.yes' : 'common.no'), kind: 'fit', priority: 3, labelled: true, sort: 'default' },
          { id: 'proxy', label: t('acme.proxy'), cell: (a) => (proxyIsOn(a) ? a.proxy_slug : '—'), kind: 'fit', priority: 3, sort: 'proxy' },
          { status: true, sort: 'state' },
        ]}
        empty={<EmptyBlock id="acme-upstream" icon="server" title={t('acme.noCaAccounts')} text={t('acme.certificateAuthoritiesDesc')}
          action={canWrite ? { label: t('acme.addCertificateAuthority'), icon: 'plus', onClick: openCreate, primary: true } : undefined} />}
        footer={{ range: list.paged ? t('table.range', { start: list.start, end: list.end, total: list.total }) : t('acme.upstreamRange', { count: list.total }) }} />
      <SlotDock>{dock}</SlotDock>
      <Modal open={showForm} onClose={closeForm} title={editingId ? t('acme.editCertificateAuthority') : t('acme.addCertificateAuthority')} size="lg" testId="acme-upstream-dialog">
        <form onSubmit={submit}>
          <div className="form-fields">
            <Input id="acme-ca-label" label={t('acme.caLabel')} value={form.label} onChange={(e) => setForm(p => ({ ...p, label: e.target.value }))}
              placeholder="ZeroSSL Production" required data-autofocus="" />
            <Input id="acme-ca-email" label={t('acme.contactEmail')} type="email" value={form.email} onChange={(e) => setForm(p => ({ ...p, email: e.target.value }))} required />
            <Input id="acme-ca-directory" label={t('acme.directoryUrl')} type="url" full value={form.directory_url} onChange={(e) => setForm(p => ({ ...p, directory_url: e.target.value }))}
              placeholder="https://acme.example.com/directory" disabled={!!editingId} helperText={editingId ? t('acme.directoryUrlImmutable') : t('acme.directoryUrlHelper')} />
            <Select id="acme-ca-key" label={t('acme.accountKeyType')} full value={form.account_key_algorithm}
              onChange={(val) => setForm(p => ({ ...p, account_key_algorithm: val }))}
              options={[
                { value: 'ES256', label: 'ECDSA P-256 (ES256)' },
                { value: 'ES384', label: 'ECDSA P-384 (ES384)' },
                { value: 'RS256', label: 'RSA 2048 (RS256)' },
              ]}
              disabled={editingId ? true : !!form.account_key_pem.trim()} helperText={editingId ? t('acme.accountKeyFixed') : undefined} />
            {!editingId && (
              <Textarea id="acme-ca-key-pem" label={t('acme.importAccountKey')} mono rows={4} spellCheck={false} value={form.account_key_pem}
                onChange={(e) => setForm(p => ({ ...p, account_key_pem: e.target.value }))}
                placeholder="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----" helperText={t('acme.importAccountKeyHelper')} />
            )}
            <Input id="acme-ca-eab-kid" label={t('acme.eabKid')} value={form.eab_kid} onChange={(e) => setForm(p => ({ ...p, eab_kid: e.target.value }))}
              placeholder="key-id-from-ca" helperText={t('acme.eabKidHelper')} />
            <SecretInput id="acme-ca-eab-hmac" label={t('acme.eabHmacKey')} value={form.eab_hmac_key} onChange={(e) => setForm(p => ({ ...p, eab_hmac_key: e.target.value }))}
              placeholder={editingId ? t('acme.eabHmacKeyKeepPlaceholder') : t('acme.eabHmacKeyPlaceholder')} helperText={t('acme.eabHmacKeyHelper')} />
            <fieldset className="field full">
              <legend>{t('acme.caTimingSettings')}</legend>
              <div className="form-fields">
                <Input id="acme-ca-poll-timeout" label={t('acme.caOrderPollTimeout')} type="number" min={30} max={600} value={form.order_poll_timeout_sec}
                  onChange={(e) => setForm(p => ({ ...p, order_poll_timeout_sec: e.target.value }))} helperText={t('acme.caOrderPollTimeoutHelper')} />
                <Input id="acme-ca-poll-interval" label={t('acme.caOrderPollInterval')} type="number" min={1} max={30} value={form.order_poll_interval_sec}
                  onChange={(e) => setForm(p => ({ ...p, order_poll_interval_sec: e.target.value }))} helperText={t('acme.caOrderPollIntervalHelper')} />
                <Input id="acme-ca-http-timeout" label={t('acme.caHttpTimeout')} type="number" min={10} max={120} value={form.http_timeout_sec}
                  onChange={(e) => setForm(p => ({ ...p, http_timeout_sec: e.target.value }))} helperText={t('acme.caHttpTimeoutHelper')} />
                <Input id="acme-ca-chain" label={t('acme.preferredChain')} value={form.preferred_chain} onChange={(e) => setForm(p => ({ ...p, preferred_chain: e.target.value }))}
                  placeholder="ISRG Root X1" helperText={t('acme.preferredChainHelper')} />
              </div>
            </fieldset>
            <ToggleSwitch id="acme-ca-proxy" label={t('acme.proxyEnabled')} checked={form.proxy_enabled} onChange={(v) => setForm(p => ({ ...p, proxy_enabled: v }))} />
            {form.proxy_enabled && (
              <Input id="acme-ca-proxy-slug" label={t('acme.proxySlug')} full value={form.proxy_slug} onChange={(e) => setForm(p => ({ ...p, proxy_slug: e.target.value.toLowerCase() }))}
                placeholder="actalis-production" helperText={t('acme.proxySlugHelper')} />
            )}
            <ToggleSwitch id="acme-ca-default" label={t('acme.useAsDefault')} checked={form.is_default} disabled={isEditingDefault}
              description={isEditingDefault ? t('acme.defaultChooseAnother') : undefined} onChange={(v) => setForm(p => ({ ...p, is_default: v }))} />
          </div>
          <div className="modal-actions">
            <button type="button" className="btn" data-action="close-modal" onClick={closeForm}>{t('common.cancel')}</button>
            <button type="submit" className="btn primary" disabled={busy || undefined}>{editingId ? t('common.save') : t('common.add')}</button>
          </div>
        </form>
      </Modal>
    </>
  )
}
