/**
 * The gabarits of the Atelier mockup, each drawn with the mockup's records, to compare them with
 * the mockup node by node (tools outside the repository). Served only by a development build
 * (`vite build --mode gabarits` or the dev server): the production build leaves it out.
 * ?screen=certificates|templates|approvals|settings|dashboard, &state=loading|error|empty,
 * &item=<template id>.
 */
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Zone, PageHead, Btn, Pill, StateFilters, TableView, SearchField, FilterSelect, TableFooter, LoadError, EmptyBlock,
  ListView, Dock, DockBody, SimpleOverview, WorkView, RecordRow, SettingsView, Card, Icon, BatchBar, IconBtn,
} from '../../components/atelier'
import * as D from './gabaritsData'

const C = D.certificates

function Certificates({ state }) {
  const [view, setView] = useState('')
  const [selected, setSelected] = useState(() => new Set())
  const [tabs, setTabs] = useState([{ key: 1, title: 'vpn.example.com', icon: 'cert' }, { key: 2, title: 'api.example.com', icon: 'cert' }])
  const [active, setActive] = useState(1)
  const [section, setSection] = useState('overview')
  const rows = state === 'empty' ? [] : C.rows.map((r, i) => ({ ...r, id: i + 1 }))
  const views = state === 'empty' ? C.views.map((v) => ({ ...v, count: 0 })) : C.views
  const head = (
    <PageHead title="Certificats" total={state === 'empty' ? '0 identités' : C.total} intent={C.intent}
      actions={<><Btn tone="quiet" icon="upload" data-action="import">Importer</Btn><Btn tone="primary" icon="plus" data-action="issue">Émettre</Btn></>} />
  )
  if (state === 'error') {
    return (
      <Zone>
        {head}
        <LoadError id="certificates" title="Impossible de charger les certificats" journal="/audit" onRetry={() => {}}
          cause={<>Cause : le serveur a répondu 503 Service indisponible à <span className="mono">GET /api/v2/certificates</span> (simulation). Les autres vues et l’inspecteur restent utilisables.</>} />
      </Zone>
    )
  }
  const columns = [
    { id: 'name', label: 'Nom commun', sort: 'name', entity: true, always: true, icon: () => 'cert', cell: (r) => r.name, skeleton: { base: 55, spread: 35 },
      extra: (r) => r.key && <span className="key-presence" role="img" title="Clé privée présente dans UCM" aria-label="Clé privée présente dans UCM"><Icon name="key" /></span> },
    { id: 'description', label: 'Description', grow: true, tone: 'muted', cell: (r) => r.description, title: (r) => r.description, skeleton: { base: 45, spread: 40 } },
    { id: 'status', label: 'État', always: true, cell: (r) => <Pill label={r.status} tone={r.tone} />, skeleton: { width: '74px', kind: 'pill' } },
    { id: 'ca', label: 'Émetteur', sort: 'ca', tone: 'muted', cell: (r) => r.ca, skeleton: { base: 50, spread: 40 } },
    { id: 'source', label: 'Source', sort: 'source', cell: (r) => <span className="source-label"><Icon name={r.sourceIcon} />{r.source}</span>, skeleton: { width: '52px' } },
    { id: 'expiry', label: 'Expiration', sort: 'days', cell: (r) => <span className={r.warn ? 'expiry-cell warn' : 'expiry-cell'}>{r.expiry}<span className={`remaining ${r.remainingTone}`}>{r.remaining}</span></span>, skeleton: { width: '92px' } },
    { id: 'key', label: 'Algorithme de clé', tone: ['small', 'muted'], cell: (r) => r.alg, skeleton: { width: '70px' } },
    { id: 'grade', label: 'Conformité', defaultHidden: true, cell: () => <span className="grade good">A</span>, skeleton: { width: '20px' } },
  ]
  const n = selected.size
  return (
    <Zone dock={state ? null : (
      <Dock label="Inspecteur de certificat" tabsLabel="Certificats ouverts" tabs={tabs} activeKey={active} onSelectTab={setActive}
        onCloseTab={(k) => { const rest = tabs.filter((x) => x.key !== k); setTabs(rest); if (active === k) setActive(rest.at(-1)?.key) }} onClose={() => setTabs([])}>
        <DockBody icon="cert" title={tabs.find((x) => x.key === active)?.title} badge={<Pill label="À renouveler" tone="warn" />}
          actions={<><Btn icon="download">Exporter</Btn><Btn tone="primary" icon="refresh">Renouveler</Btn><IconBtn quiet icon="more" title={false} label={`Autres actions pour ${tabs.find((x) => x.key === active)?.title}`} /></>} sections={[['overview', 'Aperçu'], ['chain', 'Chaîne'], ['extensions', 'Extensions'], ['history', 'Historique']]}
          section={section} onSection={setSection} sectionsLabel="Sections du certificat">
          <SimpleOverview properties={[['Émetteur', 'Services CA']]} />
        </DockBody>
      </Dock>
    )}>
      {head}
      <StateFilters views={views} active={view} onChange={setView} label="Filtrer par état" aside={C.aside} busy={state === 'loading'} />
      <TableView label="Liste des certificats" tableLabel="Tableau des certificats" kind="certificates" scrollId="cert-scroll" caption="Certificats fictifs. Activez un nom pour ouvrir son inspecteur."
        columns={columns} rows={state === 'loading' ? [] : rows} loading={state === 'loading'} rowLabel={(r) => r.name} onOpen={() => {}}
        openedId={state ? undefined : rows.find((r) => r.name === 'vpn.example.com')?.id} busy={state === 'loading'}
        rowActions={() => [{ icon: 'download', label: 'Exporter', onClick: () => {} }]} sort={{ key: 'days', asc: true }} onSort={() => {}}
        selection={{ selected, onToggle: (id) => setSelected((s) => { const x = new Set(s); if (x.has(id)) x.delete(id); else x.add(id); return x }), onTogglePage: (on) => setSelected(on ? new Set(rows.map((r) => r.id)) : new Set()) }}
        search={<>
          <SearchField id="search" name="q" label="Rechercher un certificat" placeholder={C.placeholder} value="" onChange={() => {}} />
          <FilterSelect id="ca-filter" label="Filtrer par autorité" value="" options={[{ value: '', label: C.caAll }]}
            groups={C.caGroups.map((g) => ({ label: g.label, options: g.options.map((o) => ({ value: o, label: o })) }))} />
          <FilterSelect id="source-filter" label="Filtrer par source" value="" options={C.sources.map((s, i) => ({ value: i ? s : '', label: s }))} />
        </>}
        columnsDialog={{ note: 'Le nom commun et l’état restent toujours visibles.' }} density exporter={{ label: 'Exporter la liste fictive', onClick: () => {} }}
        batch={n > 0 && (
          <BatchBar count={`${n} sélectionné${n > 1 ? 's' : ''}`} onClear={() => setSelected(new Set())}>
            <Btn icon="compare" disabled={n !== 2 || undefined}>Comparer</Btn><Btn icon="download">Exporter</Btn>
          </BatchBar>
        )}
        empty={<EmptyBlock id="certificates" icon="cert" title="Aucun certificat pour l’instant"
          text="La première émission demande une CA émettrice : l’assistant de configuration y conduit en trois étapes."
          action={{ label: 'Ouvrir l’assistant de configuration', icon: 'right', to: '/', primary: true }} />}
        card={(r) => ({ description: r.description, meta: [r.ca, r.source], note: r.key && <span className="key-note"><Icon name="key" />Clé privée dans UCM</span>, status: <Pill label={r.status} tone={r.tone} />, end: r.expiry })}
        footer={<TableFooter range={state === 'empty' ? '0–0 sur 0 certificats' : C.range}
          pagination={{ page: 1, pages: state === 'empty' ? 1 : 4, perPage: 12, sizes: [12, 24, 50], onPage: () => {}, onPerPage: () => {}, perPageLabel: 'Certificats par page' }} />}
        captionNote={C.caption[0]} />
    </Zone>
  )
}

function Templates({ item, state }) {
  const T = D.templates
  const [filter, setFilter] = useState('')
  const [open, setOpen] = useState(item || '')
  const [section, setSection] = useState('overview')
  const rows = T.rows.map((r) => ({ id: r.id, cells: r.cells, tone: r.tone }))
  const shown = rows.filter((r) => !filter || r.cells[5] === filter)
  const it = rows.find((r) => r.id === open)
  const cols = T.heads.slice(1, 5).map((label, i) => ({ id: `c${i}`, label, cell: (r) => r.cells[i + 1], grow: i === 0 }))
  return (
    <Zone dock={it && (
      <Dock label={D.templateItem.label} tabsLabel={D.templateItem.tabsLabel} tabs={[{ key: it.id, title: it.cells[0], icon: 'template' }]} activeKey={it.id} onClose={() => setOpen('')}>
        <DockBody icon="template" title={it.cells[0]} badge={<Pill label={it.cells[5]} tone={it.tone} />} sections={[['overview', D.templateItem.tab]]}
          section={section} onSection={setSection} sectionsLabel={D.templateItem.sectionsLabel}>
          <SimpleOverview properties={D.templateItem.props.map(([k, v], i, all) => [k, i === all.length - 1 ? <Pill label={v} tone={it.tone} /> : v])} summary={D.templateItem.summary} />
        </DockBody>
      </Dock>
    )}>
      <PageHead title={T.title} total={T.total} intent={T.intent} />
      <ListView filters={{ views: T.views, active: filter, onChange: setFilter, label: 'Filtrer par état', aside: T.aside }} label={T.title}
        caption={`${T.title}, données fictives. Activez un nom pour ouvrir son détail.`} icon="template" rows={state === 'loading' ? [] : shown} loading={state === 'loading'}
        title={(r) => r.cells[0]} status={(r) => <Pill label={r.cells[5]} tone={r.tone} />} columns={[...cols, { status: true }]} openedId={open}
        onOpen={(r) => setOpen(r.id)} footer={{ range: T.footer[0], note: T.footer[1] }} />
    </Zone>
  )
}

function Approvals({ state }) {
  const A = D.approvals
  const groups = A.groups.map((g) => ({
    ...g, items: g.rows.map((r) => ({
      ...r, onOpen: () => {},
      actions: (off) => r.actions.map((a) => (
        <Btn key={a.label} tone={a.cls.includes('quiet') ? 'quiet' : undefined} icon={a.icon} aria-label={a.aria} disabled={off || undefined} write>{a.label}</Btn>
      )),
    })),
  }))
  return (
    <Zone>
      <PageHead title={A.title} total={A.total} intent={A.intent} />
      <WorkView state={state === 'loading' ? 'loading' : 'ready'} hint={A.hint} groups={groups}
        bulk={() => <><Btn icon="check" write>Approuver…</Btn><Btn tone="quiet" icon="block" write>Refuser…</Btn></>}
        empty={{ title: 'Aucune demande en attente', text: 'Les demandes traitées restent dans l’historique ci-dessous ; les politiques disent quelles émissions en demandent une.' }}
        history={{ label: A.history.label, count: A.history.rows.length, children: A.history.rows.map((h) => (
          <RecordRow key={h.title} title={<button type="button" className="text-link">{h.title}</button>} meta={h.meta} badge={<Pill label={h.badge} tone={h.tone} />} />
        )) }} />
    </Zone>
  )
}

function Settings() {
  const S = D.settings
  const [values, setValues] = useState(D.settingsValues)
  const changed = Object.keys(D.settingsValues).filter((k) => String(values[k]) !== String(D.settingsValues[k]))
  const sections = D.settingsSections.map((s) => ({ ...s, test: s.test && { label: `Tester ${s.test}`, hint: D.settingsTestHint, onTest: () => {} } }))
  return (
    <Zone>
      <PageHead title={S.title} total={S.total} intent={S.intent} />
      <SettingsView sections={sections} values={values} changed={changed} tocLabel="Sections des paramètres"
        onChange={(k, v) => setValues((p) => ({ ...p, [k]: v }))} onReset={() => setValues(D.settingsValues)} onSave={() => {}}
        lastSaved={{ at: '6 nov. 2026, 10:12', by: 'administrateur' }}
        history={{ title: S.history.title, text: S.history.text, children: (
          <ul className="record-list">{S.history.rows.map((h) => <RecordRow key={h.title} title={h.title} meta={h.meta} badge={<span className="rl-meta">{h.badge}</span>} />)}</ul>
        ) }} />
    </Zone>
  )
}

function Dashboard() {
  const A = D.activityCard
  return (
    <Zone>
      <div className="scroll-view" id="view-scroll">
        <div className="dash-cards">
          <Card id="activity" title={A.title} sub={A.sub} onHide={() => {}} onCustomize={() => {}}
            tools={<a className="text-link" href="/audit">{A.tools}<Icon name="right" /></a>}>
            <div className="panel-content">
              {A.rows.map((r) => (
                <div key={r.name + r.time} className="activity-row"><Icon name={r.icon} /><div><strong>{r.label}</strong><button type="button">{r.name}</button><span className="muted small">{r.actor}</span></div><time>{r.time}</time></div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </Zone>
  )
}

export default function GabaritsPage() {
  const [params] = useSearchParams()
  const screen = params.get('screen') || 'certificates'
  const state = params.get('state') || ''
  if (screen === 'templates') return <Templates item={params.get('item')} state={state} />
  if (screen === 'approvals') return <Approvals state={state} />
  if (screen === 'settings') return <Settings />
  if (screen === 'dashboard') return <Dashboard />
  return <Certificates state={state} />
}
