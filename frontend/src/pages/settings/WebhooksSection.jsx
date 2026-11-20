import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Bell, TestTube, ArrowsClockwise, Lightning, PencilSimple, Trash, Plus, ClockCounterClockwise } from '@phosphor-icons/react'
import { Button, Badge, HelpCard, EmptyState } from '../../components'
import { webhookEventLabel } from './WebhookForm'
import WebhookDeliveriesModal from './WebhookDeliveriesModal'
import { FormGroup } from '../../components/sectioned'

export default function WebhooksSection({ webhooks, webhooksLoading, webhookTesting, handleWebhookCreate, handleWebhookEdit, handleWebhookToggle, handleWebhookTest, setWebhookConfirmDelete, hasPermission }) {
  const { t } = useTranslation()
  const [deliveriesFor, setDeliveriesFor] = useState(null)
  // Test, enable and edit write a webhook (write:settings), deleting one is delete:settings
  const canWrite = hasPermission('write:settings')
  const canDelete = hasPermission('delete:settings')
  return (
    <>

      <HelpCard variant="info" title={t('webhooks.helpTitle')}>
        {t('webhooks.helpDescription')}
      </HelpCard>

      {webhooksLoading ? (
        <div className="flex items-center justify-center py-12">
          <div className="w-6 h-6 border-2 border-accent-primary-op30 border-t-accent-primary rounded-full animate-spin" />
        </div>
      ) : webhooks.length === 0 ? (
        <EmptyState
          icon={Bell}
          title={t('webhooks.noWebhooks')}
          description={t('webhooks.noWebhooksDescription')}
          action={{ label: t('webhooks.addWebhook'), onClick: handleWebhookCreate }}
        />
      ) : (
        <FormGroup
          title={t('webhooks.configuredWebhooks')}
          actions={hasPermission('admin:system') ? (
            <Button type="button" variant="secondary" onClick={handleWebhookCreate}>
              <Plus size={16} />
              {t('webhooks.addWebhook')}
            </Button>
          ) : null}
        >
          {/* The mockup's record list: name and state, address and events, then the actions */}
          <ul className="sf-records">
            {webhooks.map(webhook => (
              <li key={webhook.id}>
                <div className="sf-record-main">
                  <span className="sf-record-title">
                    <strong>{webhook.name}</strong>
                    <Badge variant={webhook.enabled ? 'success' : 'secondary'} size="sm">
                      {webhook.enabled ? t('common.enabled') : t('common.disabled')}
                    </Badge>
                  </span>
                  <span className="sf-record-meta">{webhook.url}</span>
                  {(webhook.events || []).length > 0 && (
                    <span className="sf-record-meta">
                      {(webhook.events || []).slice(0, 3).map(ev => webhookEventLabel(t, ev)).join(', ')}
                      {(webhook.events || []).length > 3 && ` +${webhook.events.length - 3}`}
                    </span>
                  )}
                </div>
                <div className="sf-record-actions">
                  <Button type="button" variant="secondary" onClick={() => setDeliveriesFor(webhook)}
                    aria-label={t('webhooks.deliveries.title', { name: webhook.name })} title={t('webhooks.deliveries.title', { name: webhook.name })}>
                    <ClockCounterClockwise size={16} />
                  </Button>
                  {canWrite && (
                    <>
                      <Button type="button" variant="secondary" onClick={() => handleWebhookTest(webhook)} disabled={webhookTesting === webhook.id}
                        aria-label={t('webhooks.test')} title={t('webhooks.test')}>
                        {webhookTesting === webhook.id ? <ArrowsClockwise size={16} className="animate-spin" /> : <TestTube size={16} />}
                      </Button>
                      <Button type="button" variant="secondary" onClick={() => handleWebhookToggle(webhook)}
                        aria-label={webhook.enabled ? t('common.disable') : t('common.enable')} title={webhook.enabled ? t('common.disable') : t('common.enable')}>
                        <Lightning size={16} />
                      </Button>
                      <Button type="button" variant="secondary" onClick={() => handleWebhookEdit(webhook)}
                        aria-label={t('common.edit')} title={t('common.edit')}>
                        <PencilSimple size={16} />
                      </Button>
                    </>
                  )}
                  {canDelete && (
                    <Button type="button" variant="danger" onClick={() => setWebhookConfirmDelete(webhook)}
                      aria-label={t('common.delete')} title={t('common.delete')}>
                      <Trash size={16} />
                    </Button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </FormGroup>
      )}

      <WebhookDeliveriesModal
        webhook={deliveriesFor}
        onClose={() => setDeliveriesFor(null)}
        canRetry={hasPermission('write:settings') || hasPermission('admin:system')}
      />
    </>
  )
}
