import { useTranslation } from 'react-i18next'
import { Bell, TestTube, ArrowsClockwise, Lightning, PencilSimple, Trash, Plus } from '@phosphor-icons/react'
import { Button, Badge, HelpCard, DetailSection, DetailContent, DetailHeader, EmptyState } from '../../components'
import { WEBHOOK_EVENT_LABELS } from './WebhookForm'

export default function WebhooksSection({ webhooks, webhooksLoading, webhookTesting, handleWebhookCreate, handleWebhookEdit, handleWebhookToggle, handleWebhookTest, setWebhookConfirmDelete, hasPermission }) {
  const { t } = useTranslation()
  return (
    <DetailContent>
      <DetailHeader
        icon={Bell}
        title={t('webhooks.title')}
        subtitle={t('webhooks.subtitle')}
      />

      <HelpCard variant="info" title={t('webhooks.helpTitle')} className="mb-4">
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
        <DetailSection title={t('webhooks.configuredWebhooks')} icon={Bell} iconClass="icon-bg-rose">
          <div className="space-y-3">
            {webhooks.map(webhook => (
              <div key={webhook.id} className="flex items-center justify-between p-4 bg-tertiary-50 border border-border rounded-lg">
                <div className="flex items-center gap-3 min-w-0 flex-1">
                  <div className="w-10 h-10 rounded-lg bg-accent-primary-op10 flex items-center justify-center flex-shrink-0">
                    <Bell size={20} className="text-accent-primary" />
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-text-primary truncate">{webhook.name}</span>
                      <Badge variant={webhook.enabled ? 'success' : 'secondary'} size="sm">
                        {webhook.enabled ? t('common.enabled') : t('common.disabled')}
                      </Badge>
                    </div>
                    <p className="text-xs text-text-secondary truncate">{webhook.url}</p>
                    <div className="flex items-center gap-1 mt-1">
                      {(webhook.events || []).slice(0, 3).map(ev => (
                        <Badge key={ev} variant="outline" size="sm">{WEBHOOK_EVENT_LABELS[ev] || ev}</Badge>
                      ))}
                      {(webhook.events || []).length > 3 && (
                        <Badge variant="outline" size="sm">+{webhook.events.length - 3}</Badge>
                      )}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0 ml-3">
                  <Button type="button" size="sm" variant="secondary" onClick={() => handleWebhookTest(webhook)} disabled={webhookTesting === webhook.id}>
                    {webhookTesting === webhook.id ? <ArrowsClockwise size={14} className="animate-spin" /> : <TestTube size={14} />}
                  </Button>
                  <Button type="button" size="sm" variant="secondary" onClick={() => handleWebhookToggle(webhook)}>
                    <Lightning size={14} />
                  </Button>
                  <Button type="button" size="sm" variant="secondary" onClick={() => handleWebhookEdit(webhook)}>
                    <PencilSimple size={14} />
                  </Button>
                  <Button type="button" size="sm" variant="danger" onClick={() => setWebhookConfirmDelete(webhook)}>
                    <Trash size={14} />
                  </Button>
                </div>
              </div>
            ))}
            {hasPermission('admin:system') && (
              <div className="pt-2">
                <Button type="button" onClick={handleWebhookCreate}>
                  <Plus size={16} />
                  {t('webhooks.addWebhook')}
                </Button>
              </div>
            )}
          </div>
        </DetailSection>
      )}
    </DetailContent>
  )
}
