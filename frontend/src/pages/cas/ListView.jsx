/**
 * CAs page: flat list, on the list template (one action per row and a chevron;
 * everything else lives in the detail). On a phone each CA is a record that opens
 * its detail, with the same facts as the row and the chevron at its right.
 */
import { useMemo, useCallback } from 'react'
import { ShieldCheck, TreeStructure, DownloadSimple } from '@phosphor-icons/react'
import { ResponsiveDataTable } from '../../components/ui/responsive'
import { EntityName, DueDate } from '../../components/list'
import { EXPIRY_WINDOW_DAYS } from '../../lib/expiry'
import { caState, nameOfCA } from './caTree'
import { CAStatePill, CAMarks } from './CAState'

const dueOf = (row) => (row.state === 'pending' || !row.valid_to ? null : (
  <DueDate
    date={row.valid_to}
    warnDays={EXPIRY_WINDOW_DAYS}
    tone={row.state === 'revoked' ? '' : undefined}
    relative={row.state === 'revoked' ? null : undefined}
  />
))

export function ListView({ cas, allCAs, selectedId, onSelect, onDownload, loading, emptyTitle, t }) {
  const rows = useMemo(() => {
    const byId = new Map((allCAs || cas).map((ca) => [ca.id, ca]))
    return cas.map((ca) => ({
      ...ca,
      label: nameOfCA(ca) || t('cas.unnamedCA'),
      type_label: t(ca.type === 'root' ? 'common.rootCA' : 'common.intermediateCA'),
      state: caState(ca),
      parent_name: ca.type === 'root' ? '' : nameOfCA(byId.get(ca.parent_id)),
      orphan: ca.type !== 'root' && !byId.has(ca.parent_id),
      certs: ca.certs || 0,
    }))
  }, [cas, allCAs, t])

  const columns = useMemo(() => [
    {
      key: 'label',
      header: t('common.name'),
      priority: 1,
      grow: true,
      title: (row) => row.subject || row.label,
      render: (val, row) => (
        <>
          <EntityName icon={row.type === 'root' ? ShieldCheck : TreeStructure}>{val}</EntityName>
          <CAMarks ca={row} t={t} orphan={row.orphan} compact />
        </>
      ),
      mobileRender: (val, row) => (
        <div className="flex items-center justify-between gap-2 w-full">
          <span className="font-medium truncate">{val}</span>
          <span className="shrink-0"><CAStatePill ca={row} t={t} /></span>
        </div>
      ),
    },
    { key: 'type_label', header: t('common.type'), muted: true, hideOnMobile: true },
    { key: 'state', header: t('common.status'), priority: 2, hideOnMobile: true, render: (val, row) => <CAStatePill ca={row} t={t} /> },
    {
      key: 'parent_name',
      header: t('cas.parentCA'),
      priority: 3,
      muted: true,
      maxWidth: 240,
      render: (val) => val || '—',
    },
    { key: 'certs', header: t('common.certificates'), hideOnMobile: true, className: 'tabular-nums' },
    {
      key: 'valid_to',
      header: t('common.expires'),
      priority: 4,
      render: (val, row) => dueOf(row) || '—',
    },
    { key: 'key_algorithm', header: t('common.algorithm'), muted: true, small: true, hideOnMobile: true, render: (val, row) => val || row.key_type || '—' },
  ], [t])

  const card = useCallback((row) => ({
    meta: [
      row.type_label,
      row.parent_name,
      t('cas.certificateCount', { count: row.certs }),
      row.key_algorithm || row.key_type,
      // the row's marks, icons named for assistive technology as in the table
      <CAMarks key="marks" ca={row} t={t} orphan={row.orphan} compact />,
    ],
    status: <CAStatePill ca={row} t={t} />,
    end: dueOf(row),
  }), [t])

  return (
    <ResponsiveDataTable
      variant="list"
      data={rows}
      columns={columns}
      loading={loading}
      onRowClick={onSelect}
      card={card}
      cardChevron
      selectedId={selectedId}
      rowLabel={(row) => row.label}
      tableLabel={t('common.cas')}
      rangeLabel={({ start, end, total }) => t('cas.range', { start, end, count: total })}
      sortable
      defaultSort={{ key: 'label', direction: 'asc' }}
      rowActions={(row) => (row.state === 'pending' ? [] : [
        { label: t('cas.downloadCertificate'), icon: DownloadSimple, onClick: () => onDownload?.(row) },
      ])}
      emptyIcon={ShieldCheck}
      emptyTitle={emptyTitle}
    />
  )
}
