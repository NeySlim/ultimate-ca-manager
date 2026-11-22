/**
 * CAs page: the flat list of the authorities, in the mockup's module table (`listView()`): name with
 * its chips, type, state, parent, certificates, expiry, algorithm; sorted and paged on the page, one
 * action per row and the chevron that shows the authority beside the list. On a phone each one is a record.
 */
import { useMemo } from 'react'
import { DataTable, TableFooter, useClientList, useSortParam } from '../../components/atelier'
import { formatDate } from '../../lib/utils'
import { caMarks, caState, nameOfCA } from './caTree'
import { CAStatePill, CAMarks } from './CAState'

const STATE_ORDER = { active: 0, expiring: 1, pending: 2, expired: 3, revoked: 4 }
const SORTERS = {
  name: (r) => r.label,
  type: (r) => r.type_label,
  state: (r) => STATE_ORDER[r.state],
  parent: (r) => r.parent_name,
  certs: (r) => r.certs,
  expiry: (r) => (r.valid_to ? Date.parse(r.valid_to) : null),
  algorithm: (r) => r.algorithm,
}
const BY_NAME = { key: 'name', asc: true }
const SORT_KEYS = Object.keys(SORTERS)

/** resetKey: the search and the view, whose change goes back to page one. */
export function CAList({ cas, allCAs, selectedId, onSelect, onDownload, empty, resetKey, t }) {
  const all = useMemo(() => {
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
    // Equal values keep the order of the ids, as before the sort
    return list.sort((a, b) => a.id - b.id)
  }, [cas, allCAs, t])
  // The sort lives in the address (?sort=&order=), the name ascending by default
  const sortParam = useSortParam(BY_NAME, SORT_KEYS)
  const list = useClientList(all, { sorts: SORTERS, sortParam, resetKey })

  const columns = [
    { id: 'name', label: t('common.name'), sort: 'name', kind: 'entity', priority: 1, grow: true, title: (r) => r.subject || r.label,
      icon: (r) => (r.type === 'root' ? 'shield' : 'branch'), cell: (r) => r.label,
      // No box for a CA without a badge: an empty group would still count in the name's floor (G5)
      extra: (r) => (caMarks(r, t, { orphan: r.orphan }).length ? <span className="ca-badges"><CAMarks ca={r} t={t} orphan={r.orphan} /></span> : null) },
    { id: 'type', label: t('common.type'), sort: 'type', kind: 'fit', priority: 3, tone: 'muted', cell: (r) => r.type_label },
    { id: 'state', label: t('common.status'), sort: 'state', kind: 'fit', priority: 1, cell: (r) => <CAStatePill ca={r} t={t} /> },
    { id: 'parent', label: t('cas.parentCA'), sort: 'parent', kind: 'text', priority: 2, tone: 'muted', cell: (r) => r.parent_name || '—' },
    { id: 'certs', label: t('common.certificates'), sort: 'certs', kind: 'number', priority: 3, cell: (r) => r.certs },
    { id: 'expiry', label: t('certificates.expiry'), sort: 'expiry', kind: 'fit', priority: 2, cell: (r) => (r.valid_to && r.state !== 'pending' ? formatDate(r.valid_to, { time: false }) : '—') },
    { id: 'algorithm', label: t('common.algorithm'), sort: 'algorithm', kind: 'fit', priority: 3, tone: ['muted', 'small'], cell: (r) => r.algorithm || '—' },
  ]

  return (
    <DataTable
      kind="module"
      scrollId="ca-list-scroll"
      recordsId="ca-records"
      label={t('common.cas')}
      caption={t('common.cas')}
      columns={columns}
      rows={list.rows}
      rowLabel={(r) => r.label}
      onOpen={onSelect}
      openLabel={(r) => t('cas.side.show', { name: r.label })}
      openedId={selectedId}
      sort={list.sort}
      onSort={list.onSort}
      rowActions={(r) => (r.state === 'pending' ? [] : [{ icon: 'download', label: t('cas.downloadCertificate'), onClick: () => onDownload?.(r) }])}
      card={(r) => ({
        meta: [r.type_label, r.parent_name, t('cas.certificateCount', { count: r.certs }), r.algorithm,
          caMarks(r, t, { orphan: r.orphan }).length > 0 && <span key="marks" className="ca-badges"><CAMarks ca={r} t={t} orphan={r.orphan} /></span>],
        status: <CAStatePill ca={r} t={t} />,
        end: r.valid_to && r.state !== 'pending' ? formatDate(r.valid_to, { time: false }) : undefined,
      })}
      empty={empty}
      footer={list.total > 0 && <TableFooter range={t('cas.range', { start: list.start, end: list.end, count: list.total })} pagination={list.pagination} />}
    />
  )
}

export default CAList
