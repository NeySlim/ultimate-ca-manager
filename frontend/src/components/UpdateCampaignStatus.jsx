/**
 * HA rolling update: target version, nodes done, node in progress, node where it stopped and why,
 * as a record of the mockup's list with its properties under it.
 */
import { useTranslation } from 'react-i18next'
import { Btn, Pill, Props, RecordList, RecordRow } from './atelier'
import { Notice } from './atelier/Form'

const STATUS_TONE = { running: 'warn', stopped: 'bad', done: 'good' }
const STATUS_ICON = { running: 'refresh' }

export function UpdateCampaignStatus({ campaign, onResume, resuming = false }) {
  const { t } = useTranslation()
  if (!campaign) return null
  const done = campaign.done || []
  const families = Object.entries(campaign.families || {})
    .map(([node, family]) => `${node}: ${family || t('common.unknown')}`).join(', ')
  const pending = (campaign.order || []).filter(
    (node) => !done.includes(node) && node !== campaign.current?.node && node !== campaign.failed?.node
  )

  return (
    <div className="settings-stack" data-testid="update-campaign">
      <RecordList>
        <RecordRow title={t('settings.updateCampaign.title', { version: campaign.target })}
          badge={<Pill tone={STATUS_TONE[campaign.status] || 'muted'} icon={STATUS_ICON[campaign.status]} label={t(`settings.updateCampaign.status.${campaign.status}`)} />}
          action={campaign.status === 'stopped' && onResume && (
            <Btn icon="refresh" onClick={onResume} disabled={resuming}>{t('settings.updateCampaign.resume')}</Btn>
          )} />
      </RecordList>
      <Props items={[
        [t('settings.updateCampaign.nodesDone'), done.length ? done.join(', ') : t('settings.updateCampaign.none')],
        [t('settings.updateCampaign.currentNode'), campaign.current?.node || t('settings.updateCampaign.none')],
        pending.length > 0 && [t('settings.updateCampaign.pending'), pending.join(', ')],
        families && [t('settings.updateCampaign.packages'), families],
      ]} />
      {campaign.failed && (
        <Notice tone="bad">{t('settings.updateCampaign.failed', { node: campaign.failed.node, reason: campaign.failed.reason })}</Notice>
      )}
    </div>
  )
}

export default UpdateCampaignStatus
