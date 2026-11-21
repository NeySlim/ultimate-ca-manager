/**
 * CAs page: the flat list of the authorities, in the mockup's module table (`listView()`): name with
 * its chips, type, state, parent, certificates, expiry, algorithm; sorted on the page, one action per
 * row and the chevron that shows the authority beside the list. On a phone each one is a record.
 */
import { useMemo, useState } from 'react'
import { DataTable } from '../../components/atelier'
import { formatDate } from '../../lib/utils'
import { caState, nameOfCA } from './caTree'
import { CAStatePill, CAMarks } from './CAState'

const STATE_ORDER = { active: 0, expiring: 1, pending: 2, expired: 3, revoked: 4 }
const SORTERS = {
  name: (r) => r.label.toLowerCase(),
  type: (r) => r.type_label,
  state: (r) => STATE_ORDER[r.state],
  parent: (r) => r.parent_name.toLowerCase(),
  certs: (r) => r.certs,
  expiry: (r) => (r.valid_to ? Date.parse(r.valid_to) : Infinity),
  algorithm: (r) => r.algorithm,
}

export function CAList({ cas, allCAs, selectedId, onSelect, onDownload, empty, t }) {
  const [sort, setSort] = useState({ key: 'name', asc: true })
  const rows = useMemo(() => {
    const byId = new Map((allCAs || cas).map((ca) => [ca.id, ca]))
    const list = cas.map((ca) => ({
      ...ca,
      label: nameOfCA(ca) || t('cas.unnamedCA'),
      type_label: t(ca.type === 'root' ? 'common.rootCA' : 'common.intermediateCA'),
      state: caState(ca),
      parent_name: ca.type === 'root' ? '' : nameOfCA(byId.get(ca.parent_id)),
      orphan: ca.type !== 'root' && !byId.has(ca.parent_id),
      certs: ca.certs || 0,
      algorithm: ca.key_type || ca.key_algorithm || '',
    }))
    const key = SORTERS[sort.key]
    return list.sort((a, b) => {
      const x = key(a)
      const y = key(b)
      const order = x < y ? -1 : x > y ? 1 : a.id - b.id
      return sort.asc ? order : -order
    })
  }, [cas, allCAs, sort, t])

  const columns = [
    { id: 'name', label: t('common.name'), sort: 'name', entity: true, grow: true, title: (r) => r.subject || r.label,
      icon: (r) => (r.type === 'root' ? 'shield' : 'branch'), cell: (r) => r.label,
      extra: (r) => <span className="ca-badges"><CAMarks ca={r} t={t} orphan={r.orphan} /></span> },
    { id: 'type', label: t('common.type'), sort: 'type', tone: 'muted', fit: true, cell: (r) => r.type_label },
    { id: 'state', label: t('common.status'), sort: 'state', fit: true, cell: (r) => <CAStatePill ca={r} t={t} /> },
    { id: 'parent', label: t('cas.parentCA'), sort: 'parent', tone: 'muted', cell: (r) => r.parent_name || '—' },
    { id: 'certs', label: t('common.certificates'), sort: 'certs', fit: true, cell: (r) => r.certs },
    { id: 'expiry', label: t('common.expires'), sort: 'expiry', fit: true, cell: (r) => (r.valid_to && r.state !== 'pending' ? formatDate(r.valid_to, { time: false }) : '—') },
    { id: 'algorithm', label: t('common.algorithm'), sort: 'algorithm', tone: ['muted', 'small'], fit: true, cell: (r) => r.algorithm || '—' },
  ]

  return (
    <DataTable
      kind="module"
      scrollId="ca-list-scroll"
      recordsId="ca-records"
      label={t('common.cas')}
      caption={t('common.cas')}
      columns={columns}
      rows={rows}
      rowLabel={(r) => r.label}
      onOpen={onSelect}
      openLabel={(r) => t('cas.side.show', { name: r.label })}
      openedId={selectedId}
      sort={sort}
      onSort={(key) => setSort((s) => ({ key, asc: s.key === key ? !s.asc : true }))}
      rowActions={(r) => (r.state === 'pending' ? [] : [{ icon: 'download', label: t('cas.downloadCertificate'), onClick: () => onDownload?.(r) }])}
      card={(r) => ({
        meta: [r.type_label, r.parent_name, t('cas.certificateCount', { count: r.certs }), r.algorithm,
          <span key="marks" className="ca-badges"><CAMarks ca={r} t={t} orphan={r.orphan} /></span>],
        status: <CAStatePill ca={r} t={t} />,
        end: r.valid_to && r.state !== 'pending' ? formatDate(r.valid_to, { time: false }) : undefined,
      })}
      empty={empty}
    />
  )
}

export default CAList
