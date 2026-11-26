/**
 * SSH hosts (issue #451): the servers enrolled with a host CA by the SSH agent, the state of the
 * certificate each presents, whether it renews itself and when its agent last pulled a KRL, with
 * the revoke and pause actions; and the single-use enrollment tokens, shown once at creation.
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  Zone, Btn, IconBtn, Pill, PageHead, Toolbar, SearchField, FilterSelect, ListView, Dock, DockBody,
  Section, Facts, EmptyBlock, NoMatch, Input, Select, Textarea, AtelierDialog, Notice,
} from '../components/atelier'
import { sshHostsService, sshCasService } from '../services'
import { useNotification } from '../contexts'
import { usePermission, useClipboard } from '../hooks'
import { useDockSelection } from '../components/atelier/useDockParam'
import { copyRow, fact } from '../components/atelier/facts'
import { PhoneMoreActions } from './pki/PhoneMoreActions'
import { formatDate } from '../lib/utils'

const HOST_SECTIONS = ['overview', 'agent']
const VALIDITY_PRESETS = [
  { value: '', seconds: null },
  { value: '7d', seconds: 604800 },
  { value: '30d', seconds: 2592000 },
  { value: '90d', seconds: 7776000 },
  { value: '365d', seconds: 31536000 },
]
const LIFETIMES = [{ value: '900', key: '15m' }, { value: '3600', key: '1h' }, { value: '86400', key: '24h' }, { value: '604800', key: '7d' }]

function hostStatus(host, t) {
  if (host.state === 'revoked') return { label: t('sshHosts.stateRevoked'), tone: 'bad', icon: 'block' }
  if (host.state === 'expired') return { label: t('sshHosts.stateExpired'), tone: 'bad', icon: 'warning' }
  return { label: t('sshHosts.stateValid'), tone: 'good', icon: 'check' }
}

function tokenStatus(token, t) {
  const tones = { active: 'good', used: '', expired: 'muted', revoked: 'bad' }
  return { label: t(`sshHosts.token.state.${token.state}`), tone: tones[token.state] ?? '' }
}

/** The command a server runs with its token: the token in the environment, never in the script. */
const enrollCommand = (origin, caRefid, token) => `curl -fsSL ${origin}/ssh/setup/${caRefid}/agent | sudo UCM_ENROLL_TOKEN=${token} sh`

export default function SSHHostsPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const view = params.get('view') === 'tokens' ? 'tokens' : 'hosts'
  const setView = (next) => setParams((p) => { const q = new URLSearchParams(p); if (next === 'tokens') q.set('view', 'tokens'); else q.delete('view'); q.delete('item'); return q })
  const { showSuccess, showError, showConfirm } = useNotification()
  const { canWrite, canRead } = usePermission()
  const canListCas = canRead('ssh_cas')

  const [hosts, setHosts] = useState([])
  const [counts, setCounts] = useState({ valid: 0, expired: 0, revoked: 0, total: 0 })
  const [tokens, setTokens] = useState([])
  const [cas, setCas] = useState([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(25)
  const [total, setTotal] = useState(0)
  const [state, setState] = useState('')
  const [caFilter, setCaFilter] = useState('')
  const [search, setSearch] = useState('')
  const [dialog, setDialog] = useState(null)
  const dock = useDockSelection(hosts, { ready: !loading, sections: HOST_SECTIONS })
  const open = view === 'hosts' ? dock.selected : null

  const seq = useRef(0)
  const load = useCallback(async () => {
    const mine = ++seq.current
    setLoading(true)
    try {
      const query = { page, per_page: perPage }
      if (state) query.state = state
      if (caFilter) query.ca_id = caFilter
      if (search) query.search = search
      const [hostsRes, tokensRes, casRes] = await Promise.all([
        sshHostsService.getAll(query),
        sshHostsService.getTokens(),
        canListCas ? sshCasService.getAll() : Promise.resolve({ data: [] }),
      ])
      if (mine !== seq.current) return
      setHosts(hostsRes.data || [])
      setTotal(hostsRes.meta?.total || 0)
      setCounts(hostsRes.meta?.counts || { valid: 0, expired: 0, revoked: 0, total: 0 })
      setTokens(tokensRes.data || [])
      setCas((casRes.data || []).filter((ca) => ca.ca_type === 'host'))
    } catch (error) {
      showError(error.message || t('sshHosts.loadFailed'))
    } finally {
      if (mine === seq.current) setLoading(false)
    }
    // Only the query reloads: a new t or notifier on a render must not
  }, [page, perPage, state, caFilter, search, canListCas]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { load() }, [load])

  const revokeHost = async (host) => {
    const confirmed = await showConfirm(t('sshHosts.revokeConfirm', { name: host.name }), {
      title: t('sshHosts.revokeHost'), confirmText: t('sshHosts.revokeHost'), variant: 'danger',
    })
    if (!confirmed) return
    try {
      const res = await sshHostsService.revoke(host.id)
      showSuccess(t('sshHosts.revoked', { name: host.name }))
      if (open?.id === host.id) dock.select(res.data)
      load()
    } catch (error) {
      showError(error.message || t('common.operationFailed'))
    }
  }

  const toggleRenewal = async (host) => {
    try {
      const res = await sshHostsService.setAutoRenew(host.id, !host.auto_renew)
      showSuccess(res.data.auto_renew ? t('sshHosts.renewalResumed', { name: host.name }) : t('sshHosts.renewalPaused', { name: host.name }))
      if (open?.id === host.id) dock.select(res.data)
      load()
    } catch (error) {
      showError(error.message || t('common.operationFailed'))
    }
  }

  const revokeToken = async (token) => {
    try {
      await sshHostsService.revokeToken(token.id)
      showSuccess(t('sshHosts.token.revoked', { prefix: token.token_prefix }))
      load()
    } catch (error) {
      showError(error.message || t('common.operationFailed'))
    }
  }

  const pill = (s) => <Pill label={s.label} tone={s.tone} icon={s.icon} />
  const principals = (h) => (h.principals || []).join(', ') || '—'
  const when = (v) => (v ? formatDate(v, { time: true }) : null)
  // A revoked host never renews: its renewal is no state
  const renewalPill = (h) => (h.state === 'revoked' ? '—' : h.auto_renew
    ? <Pill label={t('sshHosts.renewalOn')} tone="good" icon="refresh" />
    : <Pill label={t('sshHosts.renewalOff')} tone="muted" icon="block" />)
  const writable = canWrite('ssh')
  const newToken = writable ? { label: t('sshHosts.token.create'), icon: 'plus', onClick: () => setDialog('token'), primary: true } : undefined
  const narrowed = Boolean(state || caFilter || search)
  const pages = Math.max(1, Math.ceil(total / perPage))
  const changeFilter = (set) => (v) => { set(v); setPage(1) }

  const hostActions = (h) => (writable && h.state !== 'revoked' ? [
    { icon: h.auto_renew ? 'block' : 'refresh', label: h.auto_renew ? t('sshHosts.pauseRenewal') : t('sshHosts.resumeRenewal'), write: true, onClick: toggleRenewal },
    { icon: 'close', label: t('sshHosts.revokeHost'), write: true, onClick: revokeHost },
  ] : [])

  const hostDock = open && (
    <Dock label={t('atelier.detailOf', { name: t('sshHosts.title') })} tabsLabel={t('atelier.openItem')} activeKey={open.id}
      tabs={[{ key: open.id, title: open.name, icon: 'terminal' }]} onClose={() => dock.select(null)}>
      <DockBody icon="terminal" title={open.name} badge={pill(hostStatus(open, t))}
        section={dock.section} onSection={dock.setSection} sectionsLabel={t('atelier.sectionsOf', { name: open.name })}
        sections={[['overview', t('atelier.overview')], ['agent', t('sshHosts.agent')]]}
        actions={writable && open.state !== 'revoked' && <>
          <Btn icon={open.auto_renew ? 'block' : 'refresh'} id="ssh-host-renewal" onClick={() => toggleRenewal(open)}>
            {open.auto_renew ? t('sshHosts.pauseRenewal') : t('sshHosts.resumeRenewal')}
          </Btn>
          <Btn tone="danger" icon="block" id="ssh-host-revoke" onClick={() => revokeHost(open)}>{t('sshHosts.revokeHost')}</Btn>
        </>}>
        {dock.section === 'overview' && (
          <div className="module-detail">
            <Section title={t('sshHosts.certificate')}>
              <Facts items={[
                { label: t('sshCertificates.principals'), value: principals(open), long: true },
                fact(t('sshCertificates.caName'), open.ca_name),
                fact(t('sshCertificates.validFrom'), when(open.valid_from)),
                fact(t('sshCertificates.validTo'), when(open.valid_to)),
                [t('atelier.state'), pill(hostStatus(open, t))],
                open.certificate_id ? { label: t('sshCertificates.serial'), value: String(open.certificate_serial ?? '—'), kind: 'hex' } : null,
              ].filter(Boolean)} />
            </Section>
            <Section title={t('sshHosts.hostKey')}>
              <Facts items={[
                fact(t('common.keyType'), open.key_type),
                copyRow(t('sshCertificates.fingerprint'), open.fingerprint, undefined, { long: true }),
              ]} />
            </Section>
          </div>
        )}
        {dock.section === 'agent' && (
          <div className="module-detail">
            <Section title={t('sshHosts.agent')}>
              <Facts items={[
                [t('sshHosts.autoRenew'), renewalPill(open)],
                fact(t('sshHosts.renewAt'), t('sshHosts.renewAtValue', { percent: open.renew_percent })),
                fact(t('sshHosts.enrolledAt'), when(open.enrolled_at)),
                fact(t('sshHosts.enrolledFrom'), open.enrolled_ip),
                fact(t('sshHosts.lastRenewed'), when(open.last_renewed_at)),
                fact(t('sshHosts.lastSeen'), when(open.last_seen_at)),
                // Only what the agent reported: a pull that did not name the host is not invented
                fact(t('sshHosts.lastKrlSync'), when(open.last_krl_sync_at), { absent: t('sshHosts.notReported') }),
              ]} />
            </Section>
            {open.state === 'revoked' && <Notice tone="warn">{t('sshHosts.revokedNotice')}</Notice>}
          </div>
        )}
      </DockBody>
    </Dock>
  )

  const switchView = view === 'hosts'
    ? <Btn tone="quiet" icon="key" id="ssh-hosts-tokens" onClick={() => setView('tokens')}>{t('sshHosts.token.title')}</Btn>
    : <Btn tone="quiet" icon="terminal" id="ssh-hosts-list" onClick={() => setView('hosts')}>{t('sshHosts.title')}</Btn>

  return (
    <Zone dock={hostDock} after={<>
      {dialog === 'token' && (
        <AtelierDialog title={t('sshHosts.token.create')} subtitle={t('sshHosts.token.createHint')} size="wide" onClose={() => setDialog(null)} returnTo="ssh-token-new">
          <TokenForm cas={cas} canListCas={canListCas} onDone={load} onCancel={() => setDialog(null)} />
        </AtelierDialog>
      )}
    </>}>
      <PageHead title={view === 'hosts' ? t('sshHosts.title') : t('sshHosts.token.title')}
        total={view === 'hosts' ? t('sshHosts.subtitle', { count: counts.total || 0 }) : t('sshHosts.token.subtitle', { count: tokens.length })}
        intent={view === 'hosts' ? t('sshHosts.intent') : t('sshHosts.token.intent')}
        actions={<>
          {switchView}
          <PhoneMoreActions title={t('sshHosts.title')} items={[
            view === 'hosts' ? { id: 'tokens', icon: 'key', label: t('sshHosts.token.title'), onClick: () => setView('tokens') }
              : { id: 'hosts', icon: 'terminal', label: t('sshHosts.title'), onClick: () => setView('hosts') },
            { id: 'ssh-cas', icon: 'terminal', label: t('sshCas.title'), onClick: () => navigate('/ssh/cas') },
          ]} />
          {newToken && <Btn tone="primary" icon="plus" id="ssh-token-new" onClick={newToken.onClick}>{newToken.label}</Btn>}
        </>} />
      {view === 'hosts' ? (
        <ListView label={t('sshHosts.title')} caption={t('sshHosts.caption')} icon="terminal" rows={hosts} loading={loading && !hosts.length}
          filters={{
            views: [
              { id: '', label: t('common.all'), count: counts.total || 0 },
              { id: 'valid', label: t('sshHosts.stateValid'), count: counts.valid || 0 },
              { id: 'expired', label: t('sshHosts.stateExpired'), count: counts.expired || 0 },
              { id: 'revoked', label: t('sshHosts.stateRevoked'), count: counts.revoked || 0 },
            ],
            active: state, onChange: changeFilter(setState), label: t('sshHosts.filterByState'),
          }}
          toolbar={(
            <Toolbar>
              <SearchField id="ssh-host-search" name="q" label={t('sshHosts.searchLabel')} placeholder={t('sshHosts.searchLabel')}
                value={search} onChange={changeFilter(setSearch)} />
              {cas.length > 0 && (
                <FilterSelect id="ssh-host-ca" label={t('sshCertificates.caName')} value={caFilter} onChange={changeFilter(setCaFilter)}
                  options={[{ value: '', label: t('common.allCAs') }, ...cas.map((ca) => ({ value: String(ca.id), label: ca.name || ca.descr }))]} />
              )}
            </Toolbar>
          )}
          title={(h) => h.name} status={(h) => pill(hostStatus(h, t))} openedId={open?.id} onOpen={dock.select}
          columns={[
            { id: 'principals', label: t('sshCertificates.principals'), cell: principals, kind: 'text', grow: true, priority: 3 },
            { id: 'expires', label: t('certificates.expiry'), cell: (h) => (h.valid_to ? formatDate(h.valid_to) : '—'), kind: 'fit', priority: 2, labelled: true },
            { id: 'renewal', label: t('sshHosts.autoRenew'), cell: renewalPill, kind: 'fit', priority: 2 },
            { id: 'krl', label: t('sshHosts.lastKrlSync'), cell: (h) => (h.last_krl_sync_at ? formatDate(h.last_krl_sync_at, { time: true }) : '—'), kind: 'fit', priority: 4, muted: true },
            { id: 'ca', label: t('sshCertificates.caName'), cell: (h) => h.ca_name || '—', kind: 'text', priority: 4, muted: true },
            { status: true },
          ]}
          rowActions={hostActions}
          empty={narrowed ? (
            <NoMatch title={t('table.noResults')} text={t('table.adjustFilters')} resetLabel={t('table.clearFilters')}
              onReset={() => { setSearch(''); setState(''); setCaFilter(''); setPage(1) }} />
          ) : (
            <EmptyBlock id="ssh-hosts" icon="terminal" title={t('sshHosts.noData')} text={t('sshHosts.noDataDescription')} action={newToken} />
          )}
          footer={total > 0 ? {
            range: t('sshHosts.pageRange', { start: (page - 1) * perPage + 1, end: Math.min(page * perPage, total), count: total }),
            pagination: { page, pages, perPage, sizes: [10, 25, 50, 100], onPage: setPage, onPerPage: (n) => { setPerPage(n); setPage(1) } },
          } : undefined} />
      ) : (
        <ListView label={t('sshHosts.token.title')} caption={t('sshHosts.token.caption')} icon="key" rows={tokens} loading={loading && !tokens.length}
          title={(tk) => tk.descr || (tk.principals || [])[0] || tk.token_prefix} status={(tk) => pill(tokenStatus(tk, t))}
          columns={[
            { id: 'prefix', label: t('sshHosts.token.prefix'), cell: (tk) => <span className="mono">{tk.token_prefix}…</span>, kind: 'fit', priority: 3 },
            { id: 'principals', label: t('sshCertificates.principals'), cell: principals, kind: 'text', grow: true, priority: 3 },
            { id: 'ca', label: t('sshCertificates.caName'), cell: (tk) => tk.ca_name || '—', kind: 'text', priority: 4, muted: true },
            { id: 'expires', label: t('sshHosts.token.expires'), cell: (tk) => formatDate(tk.expires_at, { time: true }), kind: 'fit', priority: 2, labelled: true },
            { status: true },
          ]}
          rowActions={(tk) => (writable && tk.state === 'active' ? [{ icon: 'close', label: t('sshHosts.token.revoke'), write: true, onClick: revokeToken }] : [])}
          empty={<EmptyBlock id="ssh-tokens" icon="key" title={t('sshHosts.token.noData')} text={t('sshHosts.token.noDataDescription')} action={newToken} />} />
      )}
    </Zone>
  )
}

function TokenForm({ cas, canListCas, onDone, onCancel }) {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  const { copy, isCopied } = useClipboard()
  const [caId, setCaId] = useState('')
  const [names, setNames] = useState('')
  const [validity, setValidity] = useState('')
  const [lifetime, setLifetime] = useState('3600')
  const [renewPercent, setRenewPercent] = useState('30')
  const [descr, setDescr] = useState('')
  const [busy, setBusy] = useState(false)
  const [created, setCreated] = useState(null)

  useEffect(() => { if (cas.length && !caId) setCaId(String(cas[0].id)) }, [cas]) // eslint-disable-line react-hooks/exhaustive-deps

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    try {
      const preset = VALIDITY_PRESETS.find((p) => p.value === validity)
      const data = {
        ca_id: parseInt(caId, 10),
        principals: names.split(/[\s,]+/).map((n) => n.trim()).filter(Boolean),
        lifetime_seconds: parseInt(lifetime, 10),
        renew_percent: parseInt(renewPercent, 10),
      }
      if (preset?.seconds) data.validity_seconds = preset.seconds
      if (descr.trim()) data.descr = descr.trim()
      const res = await sshHostsService.createToken(data)
      setCreated({ ...res.data, ca: cas.find((ca) => String(ca.id) === caId) })
      showSuccess(t('sshHosts.token.created'))
      onDone()
    } catch (error) {
      showError(error.message || t('common.operationFailed'))
    } finally {
      setBusy(false)
    }
  }

  if (created) {
    const command = enrollCommand(window.location.origin, created.ca?.refid, created.token)
    return (
      <div>
        <Notice tone="warn">{t('sshHosts.token.shownOnce')}</Notice>
        <div className="form-fields">
          <section className="field full" aria-labelledby="ssh-token-value">
            <span id="ssh-token-value">{t('sshHosts.token.value')}</span>
            <div className="command-line">
              <code className="mono" data-testid="ssh-token-secret">{created.token}</code>
              <IconBtn icon={isCopied('token') ? 'check' : 'copy'} label={t('common.copy')} onClick={() => copy(created.token, 'token')} />
            </div>
          </section>
          <section className="field full" aria-labelledby="ssh-token-command">
            <span id="ssh-token-command">{t('sshHosts.token.command')}</span>
            <div className="command-line">
              <code className="mono" data-testid="ssh-token-command">{command}</code>
              <IconBtn icon={isCopied('command') ? 'check' : 'copy'} label={t('common.copy')} onClick={() => copy(command, 'command')} />
            </div>
            <small>{t('sshHosts.token.commandHint', { expires: formatDate(created.expires_at, { time: true }) })}</small>
          </section>
        </div>
        <div className="modal-actions">
          <Btn tone="primary" write={false} data-action="close-modal" onClick={onCancel}>{t('common.close')}</Btn>
        </div>
      </div>
    )
  }

  return (
    <form onSubmit={submit}>
      <div className="form-fields">
        <Select label={t('sshHosts.token.hostCa')} value={caId} onChange={setCaId} required
          options={cas.map((ca) => ({ value: String(ca.id), label: ca.name || ca.descr }))} placeholder={t('sshHosts.token.hostCa')}
          error={!canListCas ? t('sshHosts.token.needsCaRead') : (!cas.length ? t('sshHosts.token.noHostCa') : undefined)} />
        <Textarea label={t('sshHosts.token.principals')} value={names} onChange={(e) => setNames(e.target.value)} rows={2} mono required
          placeholder="web01.example.com, web01" hint={t('sshHosts.token.principalsHint')} />
        <Select label={t('sshHosts.token.validity')} value={validity} onChange={setValidity}
          options={VALIDITY_PRESETS.map((p) => ({ value: p.value, label: p.value ? t(`sshCertificates.presets.${p.value}`) : t('sshHosts.token.caDefault') }))} />
        <Select label={t('sshHosts.token.lifetime')} value={lifetime} onChange={setLifetime}
          options={LIFETIMES.map((l) => ({ value: l.value, label: t(`sshHosts.token.lifetimes.${l.key}`) }))} />
        <Input type="number" label={t('sshHosts.token.renewPercent')} value={renewPercent} min={5} max={90}
          onChange={(e) => setRenewPercent(e.target.value)} hint={t('sshHosts.token.renewPercentHint')} />
        <Input label={t('common.description')} value={descr} onChange={(e) => setDescr(e.target.value)} maxLength={255} full />
      </div>
      <div className="modal-actions">
        <button type="button" className="btn" data-action="close-modal" onClick={onCancel}>{t('common.cancel')}</button>
        <Btn type="submit" tone="primary" icon="key" disabled={busy || !caId || !names.trim() || undefined}>{t('sshHosts.token.create')}</Btn>
      </div>
    </form>
  )
}
