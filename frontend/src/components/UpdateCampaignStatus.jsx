/**
 * HA rolling update: target version, nodes done, node in progress, node where it stopped and why.
 */
import { useTranslation } from 'react-i18next'
import { CheckCircle, Warning, ArrowsClockwise } from '@phosphor-icons/react'
import { Badge, Button } from '../components'

const STATUS_VARIANT = { running: 'info', stopped: 'danger', done: 'success' }

export function UpdateCampaignStatus({ campaign, onResume, resuming = false }) {
  const { t } = useTranslation()
  if (!campaign) return null
  const done = campaign.done || []
  const families = Object.entries(campaign.families || {})
    .map(([node, family]) => `${node}: ${family || 'unknown'}`).join(', ')
  const pending = (campaign.order || []).filter(
    (node) => !done.includes(node) && node !== campaign.current?.node && node !== campaign.failed?.node
  )

  return (
    <div className="mt-4 pt-4 border-t border-border-op50 text-sm" data-testid="update-campaign">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="font-medium text-text-primary">
            {t('settings.updateCampaign.title', { version: campaign.target })}
          </span>
          <Badge variant={STATUS_VARIANT[campaign.status] || 'secondary'} size="sm">
            {t(`settings.updateCampaign.status.${campaign.status}`)}
          </Badge>
        </div>
        {campaign.status === 'stopped' && onResume && (
          <Button variant="secondary" size="sm" onClick={onResume} disabled={resuming} className="gap-1.5">
            <ArrowsClockwise size={14} />
            {t('settings.updateCampaign.resume')}
          </Button>
        )}
      </div>
      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-text-secondary">
        <dt className="text-text-tertiary">{t('settings.updateCampaign.nodesDone')}</dt>
        <dd className="flex items-center gap-1">
          {done.length ? <><CheckCircle size={14} className="text-accent-success" />{done.join(', ')}</> : t('settings.updateCampaign.none')}
        </dd>
        <dt className="text-text-tertiary">{t('settings.updateCampaign.currentNode')}</dt>
        <dd>{campaign.current?.node || t('settings.updateCampaign.none')}</dd>
        {pending.length > 0 && (
          <>
            <dt className="text-text-tertiary">{t('settings.updateCampaign.pending')}</dt>
            <dd>{pending.join(', ')}</dd>
          </>
        )}
        {families && (
          <>
            <dt className="text-text-tertiary">{t('settings.updateCampaign.packages')}</dt>
            <dd>{families}</dd>
          </>
        )}
      </dl>
      {campaign.failed && (
        <div className="flex items-start gap-2 mt-3 p-2.5 bg-accent-danger-op15 rounded-lg text-xs text-accent-danger">
          <Warning size={16} className="shrink-0 mt-0.5" />
          <span>{t('settings.updateCampaign.failed', { node: campaign.failed.node, reason: campaign.failed.reason })}</span>
        </div>
      )}
    </div>
  )
}

export default UpdateCampaignStatus
