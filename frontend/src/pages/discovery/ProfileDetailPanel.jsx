import { Badge, CompactSection, CompactGrid, CompactField } from '../../components'
import { formatDate } from '../../lib/utils'

export default function ProfileDetailPanel({ item, t }) {
  const targets = item.targets_list || (typeof item.targets === 'string' ? (() => { try { return JSON.parse(item.targets) } catch { return item.targets.split(',') } })() : item.targets) || []
  const ports = item.ports_list || (typeof item.ports === 'string' ? (() => { try { return JSON.parse(item.ports) } catch { return item.ports.split(',') } })() : item.ports) || [443]

  const scheduleLabel = (val) => {
    if (!val) return t('discovery.manual')
    const h = Math.round(val / 3600)
    if (h < 24) return `${h}h`
    return `${Math.round(h / 24)}d`
  }

  return (
    <div className="p-4 space-y-4">
      <CompactSection title={t('common.info')}>
        <CompactGrid>
          <CompactField label={t('common.name')} value={item.name} />
          {item.description && <CompactField label={t('common.description')} value={item.description} />}
          <CompactField
            label={t('common.status')}
            value={
              <Badge variant={item.enabled ? 'success' : 'secondary'} size="sm" dot>
                {item.enabled ? t('common.enabled') : t('common.disabled')}
              </Badge>
            }
          />
          <CompactField label={t('discovery.schedule')} value={scheduleLabel(item.schedule_interval)} />
          {item.notify_email && <CompactField label={t('discovery.notifyEmail')} value={item.notify_email} />}
        </CompactGrid>
      </CompactSection>

      <CompactSection title={t('discovery.targets')}>
        <div className="space-y-1">
          {targets.map((target, i) => (
            <div key={i} className="text-sm font-mono text-text-secondary px-2 py-1 bg-bg-tertiary rounded">
              {target}
            </div>
          ))}
        </div>
      </CompactSection>

      <CompactSection title={t('discovery.ports')}>
        <div className="flex flex-wrap gap-1.5">
          {ports.map((port, i) => (
            <Badge key={i} variant="secondary" size="sm">{port}</Badge>
          ))}
        </div>
      </CompactSection>

      {item.last_scan_at && (
        <CompactSection title={t('discovery.lastScan')}>
          <CompactGrid>
            <CompactField label={t('common.date')} value={formatDate(item.last_scan_at)} />
          </CompactGrid>
        </CompactSection>
      )}
    </div>
  )
}
