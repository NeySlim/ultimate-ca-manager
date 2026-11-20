import { useMemo } from 'react'
import {
  Certificate, Info, Check, Clock, Warning, Prohibit, LinkBreak, Archive, LinkSimple, Key
} from '@phosphor-icons/react'
import { Badge } from '../../components'
import { StatusPill, SourceLabel, EntityName, RowMark, DueDate } from '../../components/list'
import { formatDate, extractCN, cn } from '../../lib/utils'
import { certificateKeyLabel } from '../../lib/certificateDetail'
import { EXPIRY_WINDOW_DAYS } from '../../lib/expiry'
import { sourceOf, sourceLabel, sourceIcon } from './certificateSources'

const GRADE_TONES = { 'A+': 'good', A: 'good', B: 'good', C: 'warn', D: 'warn', F: 'bad' }
const DUE_TONES = { expired: 'bad', expiring: 'warn', valid: '' }

/** The one state a row shows: tone, icon and label of its pill. */
export function certificateState(row, t) {
  const status = row.revoked ? 'revoked' : row.status || 'unknown'
  return {
    valid: { tone: 'good', icon: Check, label: t('common.valid') },
    expiring: { tone: 'warn', icon: Clock, label: t('certificates.views.expiring') },
    expired: { tone: 'bad', icon: Warning, label: t('common.expired') },
    revoked: { tone: 'muted', icon: Prohibit, label: t('common.revoked') },
  }[status] || { tone: 'muted', icon: Info, label: t('common.unknown') }
}

export function useCertificateColumns(t) {
  const columns = useMemo(() => {
    const statePill = (row) => <StatusPill {...certificateState(row, t)} />
    const source = (row) => {
      const value = sourceOf(row)
      return <SourceLabel icon={sourceIcon(value)} label={sourceLabel(value, t)} />
    }
    // Member of a hybrid pair (RFC 9763), titled with its role
    const roleOf = (row) => t({
      classical: 'certificates.hybrid.roleClassical', pq: 'certificates.hybrid.rolePq',
    }[row.hybrid_role] || 'certificates.hybrid.relatedCertificate')
    const issuerOf = (row) => extractCN(row.issuer) || row.issuer_name || ''
    // A revoked certificate has no deadline left to count down to
    const due = (row, className) => (
      <DueDate
        className={className}
        date={row.valid_to}
        warnDays={EXPIRY_WINDOW_DAYS}
        tone={row.revoked ? '' : DUE_TONES[row.status]}
        relative={row.revoked ? t('common.revoked') : undefined}
      />
    )

    return [
      {
        key: 'cn',
        header: t('common.commonName'),
        priority: 1,
        sortable: true,
        // Never hidden, never shortened: the name keeps 200 px at least and its whole text
        alwaysVisible: true,
        minWidth: 200,
        skeletonWidth: (i, sk) => sk(i, 55, 35),
        // One line: the name opens the detail (not while rows are ticked), quiet marks follow it
        render: (val, row, ctx) => (
          <>
            <EntityName icon={Certificate} disabled={ctx?.locked}>{val}</EntityName>
            {row.has_private_key && <RowMark icon={Key} label={t('certificates.keyHeld')} />}
            {row.related_certificate_id != null && <RowMark icon={LinkSimple} label={roleOf(row)} />}
            {row.isOrphan && (
              <RowMark icon={LinkBreak} tone="warn" label={t('certificates.orphanDescription')}>{t('certificates.orphan')}</RowMark>
            )}
            {row.archived && <RowMark icon={Archive} label={t('certificates.archivedMark')} />}
          </>
        ),
        // Mobile card: name and description on the left, state on the right
        mobileRender: (val, row) => (
          <div className="flex items-center justify-between gap-2 w-full">
            <div className="flex items-center gap-2 min-w-0 flex-1">
              <Certificate size={16} className="shrink-0 text-text-secondary" aria-hidden="true" />
              <div className="flex flex-col min-w-0">
                <span className="font-medium truncate">{val || row.cn || row.common_name || t('common.certificate')}</span>
                {row.subtitle && <span className="text-xs text-text-secondary truncate">{row.subtitle}</span>}
              </div>
              {row.has_private_key && <RowMark icon={Key} label={t('certificates.keyHeld')} />}
            </div>
            <div className="shrink-0">{statePill(row)}</div>
          </div>
        )
      },
      {
        // The description (Rename) when it says something else than the name
        key: 'descr',
        header: t('common.description'),
        sortable: true,
        hideOnMobile: true,
        muted: true,
        // The column that absorbs the width left, shortened by an ellipsis, the whole text on hover
        grow: true,
        minWidth: 64,
        accessor: (row) => row.subtitle || '',
        title: (row) => row.subtitle || '',
        render: (val, row) => row.subtitle || ''
      },
      {
        key: 'status',
        header: t('certificates.state'),
        priority: 2,
        alwaysVisible: true,
        sortable: true, // Groups by status type, then alphabetically
        hideOnMobile: true, // Shown in the name's mobile card
        skeleton: 'pill',
        skeletonWidth: 74,
        render: (val, row) => statePill(row)
      },
      {
        key: 'issuer',
        header: t('common.issuer'),
        priority: 3,
        sortable: true,
        muted: true,
        // Capped so a long authority name does not push the table; its whole name on hover
        maxWidth: 260,
        skeletonWidth: (i, sk) => sk(i, 50, 40),
        title: issuerOf,
        render: (val, row) => issuerOf(row) || '—',
        // Mobile card, under the name: who issued it and how, then when it is due
        mobileRender: (val, row) => (
          <div className="flex flex-col gap-0.5 text-xs">
            <span className="flex items-center gap-2 min-w-0">
              <span className="text-text-secondary truncate">{issuerOf(row) || '—'}</span>
              {source(row)}
              {row.isOrphan && <RowMark icon={LinkBreak} tone="warn" label={t('certificates.orphanDescription')}>{t('certificates.orphan')}</RowMark>}
            </span>
            {due(row, 'self-start')}
          </div>
        )
      },
      {
        key: 'source',
        header: t('certificates.source'),
        // Not sortable: the list API has no order by source
        sortable: false,
        hideOnMobile: true,
        skeletonWidth: 52,
        title: (row) => sourceLabel(sourceOf(row), t),
        accessor: (row) => sourceLabel(sourceOf(row), t),
        render: (val, row) => source(row)
      },
      {
        key: 'valid_to',
        header: t('certificates.expiry'),
        priority: 4,
        sortable: true,
        skeletonWidth: 92,
        render: (val, row) => due(row)
      },
      {
        key: 'key_type',
        header: t('common.keyAlgorithm'),
        hideOnMobile: true,
        sortable: true,
        muted: true,
        small: true,
        skeletonWidth: 70,
        render: (val, row) => certificateKeyLabel(row, t) || '—'
      },
      {
        key: 'compliance_grade',
        header: t('certificates.complianceColumn'),
        skeletonWidth: 20,
        sortable: true,
        hideOnMobile: true,
        defaultHidden: true,
        render: (val, row) => {
          const grade = GRADE_TONES[row.compliance_grade] ? row.compliance_grade : 'F'
          return (
            <span className={cn('lv-grade', `is-${GRADE_TONES[grade]}`)} title={`${row.compliance_score ?? 0}/100`}>{grade}</span>
          )
        }
      },
      {
        key: 'related_certificate_id',
        header: t('certificates.hybrid.column'),
        hideOnMobile: true,
        sortable: false,
        defaultHidden: true,
        render: (val, row) => (row.related_certificate_id == null
          ? <span className="text-xs text-text-tertiary">—</span>
          : (
            <Badge variant="info" size="sm" icon={LinkSimple} data-testid="hybrid-linked-badge" title={roleOf(row)}>
              {t('certificates.hybrid.linked')}
            </Badge>
          ))
      },
      {
        // When the entry was added to UCM; an in-place renewal keeps it
        key: 'created_at',
        header: t('common.created'),
        hideOnMobile: true,
        sortable: true,
        muted: true,
        small: true,
        defaultHidden: true,
        render: (val) => formatDate(val)
      }
    ]
  }, [t])

  return columns
}
