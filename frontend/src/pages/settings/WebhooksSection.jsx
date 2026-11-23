import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Btn, IconBtn, Pill, RecordList, RecordRow, SkeletonPanel, EmptyBlock } from '../../components/atelier'
import { SettingsGroup } from '../../components/atelier/SettingsView'
import { webhookEventLabel } from './WebhookForm'
import WebhookDeliveriesModal from './WebhookDeliveriesModal'

export default function WebhooksSection({ webhooks, webhooksLoading, webhookTesting, handleWebhookCreate, handleWebhookEdit, handleWebhookToggle, handleWebhookTest, setWebhookConfirmDelete, hasPermission }) {
  const { t } = useTranslation()
  const [deliveriesFor, setDeliveriesFor] = useState(null)
  // Test, enable and edit write a webhook (write:settings), deleting one is delete:settings
  const canWrite = hasPermission('write:settings')
  const canDelete = hasPermission('delete:settings')
  let body
  if (webhooksLoading) body = <SkeletonPanel label={t('common.loading')} />
  else if (webhooks.length === 0) {
    body = (
      <EmptyBlock id="webhooks" icon="bell" title={t('webhooks.noWebhooks')} text={t('webhooks.noWebhooksDescription')}
        action={{ label: t('webhooks.addWebhook'), icon: 'plus', onClick: handleWebhookCreate, primary: true }} />
    )
  } else {
    // The mockup's record list: name and state, address and events, then the actions
    body = (
      <SettingsGroup legend={t('webhooks.configuredWebhooks')} grid={false}>
        {/* Ten at first: a long list no longer pushes the sections after it thousands of pixels down */}
        <RecordList step={10}>
          {webhooks.map(webhook => {
            const events = webhook.events || []
            return (
              <RecordRow key={webhook.id} title={webhook.name}
                meta={<span className="mono">{webhook.url}</span>}
                extra={events.length > 0 && (
                  <span className="rl-meta">
                    {events.slice(0, 3).map(ev => webhookEventLabel(t, ev)).join(', ')}
                    {events.length > 3 && ` +${events.length - 3}`}
                  </span>
                )}
                badge={<Pill tone={webhook.enabled ? 'good' : 'muted'} label={webhook.enabled ? t('common.enabled') : t('common.disabled')} />}
                action={<>
                  <IconBtn icon="clock" label={t('webhooks.deliveries.title', { name: webhook.name })} onClick={() => setDeliveriesFor(webhook)} />
                  {canWrite && (
                    <>
                      <IconBtn icon="send" label={t('webhooks.test')} disabled={webhookTesting === webhook.id || undefined} onClick={() => handleWebhookTest(webhook)} />
                      <IconBtn icon={webhook.enabled ? 'block' : 'check'} write label={webhook.enabled ? t('common.disable') : t('common.enable')}
                        onClick={() => handleWebhookToggle(webhook)} />
                      <IconBtn icon="settings" label={t('common.edit')} onClick={() => handleWebhookEdit(webhook)} />
                    </>
                  )}
                  {canDelete && <IconBtn icon="close" write label={t('common.delete')} onClick={() => setWebhookConfirmDelete(webhook)} />}
                </>} />
            )
          })}
        </RecordList>
        {hasPermission('admin:system') && (
          <div className="settings-actions">
            <Btn tone="primary" icon="plus" onClick={handleWebhookCreate}>{t('webhooks.addWebhook')}</Btn>
          </div>
        )}
      </SettingsGroup>
    )
  }
  return (
    <>
      {body}
      <WebhookDeliveriesModal
        webhook={deliveriesFor}
        onClose={() => setDeliveriesFor(null)}
        canRetry={hasPermission('write:settings') || hasPermission('admin:system')}
      />
    </>
  )
}
