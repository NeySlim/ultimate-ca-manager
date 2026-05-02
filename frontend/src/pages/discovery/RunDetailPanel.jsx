import { ArrowsClockwise, CheckCircle, XCircle } from '@phosphor-icons/react'
import { Badge, CompactSection, CompactGrid, CompactField } from '../../components'
import { formatDate } from '../../lib/utils'

export default function RunDetailPanel({ item, t }) {
  const duration = item.duration_seconds
  const durationStr = duration == null ? '—' : duration < 60 ? `${Math.round(duration)}s` : `${Math.round(duration / 60)}m ${Math.round(duration % 60)}s`

  return (
    <div className="p-4 space-y-4">
      <CompactSection title={t('common.info')}>
        <CompactGrid>
          <CompactField label={t('discovery.profile')} value={item.profile_name || t('discovery.adHocScan')} />
          <CompactField
            label={t('common.status')}
            value={
              <Badge
                variant={item.status === 'completed' ? 'success' : item.status === 'running' ? 'info' : 'danger'}
                size="sm"
                icon={item.status === 'completed' ? CheckCircle : item.status === 'running' ? ArrowsClockwise : XCircle}
                dot={item.status === 'running'}
              >
                {item.status === 'completed' ? t('common.completed') : item.status === 'running' ? t('discovery.scanning') : t('common.failed')}
              </Badge>
            }
          />
        </CompactGrid>
      </CompactSection>

      <CompactSection title={t('discovery.scanResults')}>
        <CompactGrid>
          <CompactField label={t('discovery.certsFound')} value={item.certs_found ?? 0} />
          <CompactField label={t('discovery.targetsScanned')} value={item.targets_scanned ?? 0} />
        </CompactGrid>
      </CompactSection>

      <CompactSection title={t('common.timeline')}>
        <CompactGrid>
          <CompactField label={t('common.started')} value={item.started_at ? formatDate(item.started_at) : '—'} />
          <CompactField label={t('common.completed')} value={item.completed_at ? formatDate(item.completed_at) : '—'} />
          <CompactField label={t('discovery.duration')} value={durationStr} />
        </CompactGrid>
      </CompactSection>

      {item.error_message && (
        <CompactSection title={t('common.error')}>
          <div className="text-sm text-status-danger bg-bg-tertiary rounded p-2 font-mono">
            {item.error_message}
          </div>
        </CompactSection>
      )}
    </div>
  )
}
