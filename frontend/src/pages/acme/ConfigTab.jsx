import { useTranslation } from 'react-i18next'
import { FloppyDisk, Globe, ArrowsClockwise, Lightning, FileText, PencilSimple } from '@phosphor-icons/react'
import { ToggleSwitch } from '../../components/ui/ToggleSwitch'
import { Select, Button, HelpCard, CompactSection, CompactGrid, CompactField, Input, Modal } from '../../components'
import { useState, useMemo } from 'react'

/** Render markdown-like preview: paragraphs, bold, italic, auto-links */
function renderTosPreview(body) {
  if (!body?.trim()) return null
  let html = body
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
    .replace(/^- (.+)$/gm, '• $1')
    .replace(/(https?:\/\/[^\s<>()]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>')
  return html.split('\n\n').map(p => p.trim()).filter(Boolean).map(p => `<p>${p.replace(/\n/g, '<br>')}</p>`).join('')
}

export default function ConfigTab({ acmeSettings, cas, updateSetting, onSaveConfig, saving, revokeSuperseded, onRevokeSupersededChange, onToggleRevokeOnRenewal, canWrite }) {
  const { t } = useTranslation()
  const [editOpen, setEditOpen] = useState(false)
  const [editTitle, setEditTitle] = useState(acmeSettings.terms_of_service?.title || '')
  const [editBody, setEditBody] = useState(acmeSettings.terms_of_service?.body || '')

  const tos = acmeSettings.terms_of_service
  const tosExists = tos?.title || tos?.body

  // Preview of saved ToS (from props)
  const savedPreview = useMemo(() => renderTosPreview(tos?.body), [tos?.body])

  // Preview inside edit modal
  const editPreview = useMemo(() => renderTosPreview(editBody), [editBody])

  const handleOpenEdit = () => {
    setEditTitle(tos?.title || '')
    setEditBody(tos?.body || '')
    setEditOpen(true)
  }

  const handleSaveEdit = () => {
    updateSetting('terms_of_service', { title: editTitle, body: editBody })
    setEditOpen(false)
  }

  return (
    <div className="p-4 space-y-4">
      <HelpCard variant="info" title={t('common.aboutAcme')} compact>
        {t('acme.aboutAcmeDesc')}
      </HelpCard>

      <CompactSection title={t('acme.acmeServer')} icon={Globe}>
        <div className="space-y-3">
          <ToggleSwitch
            checked={acmeSettings.enabled || false}
            onChange={(val) => updateSetting('enabled', val)}
            disabled={!canWrite}
            label={t('acme.enableAcmeServer')}
            description={t('acme.enableAcmeServerDesc')}
          />

          <Select
            label={t('acme.defaultIssuingCA')}
            value={acmeSettings.issuing_ca_id?.toString() || ''}
            onChange={(val) => updateSetting('issuing_ca_id', val ? parseInt(val) : null)}
            disabled={!acmeSettings.enabled || !canWrite}
            placeholder={t('common.acmeSelectCA')}
            options={cas.map(ca => ({ 
              value: ca.id.toString(), 
              label: ca.name || ca.common_name 
            }))}
          />
        </div>
      </CompactSection>

      <CompactSection title={t('acme.renewalPolicy')} icon={ArrowsClockwise}>
        <div className="space-y-2">
          <ToggleSwitch
            checked={acmeSettings.revoke_on_renewal || false}
            onChange={onToggleRevokeOnRenewal}
            disabled={!canWrite}
            label={t('acme.revokeOnRenewal')}
            description={t('acme.revokeOnRenewalDesc')}
          />
          
          {!acmeSettings.revoke_on_renewal && acmeSettings.superseded_count > 0 && (
            <label className="flex items-center gap-3 cursor-pointer ml-7 p-2 rounded-lg hover:bg-tertiary-op50 transition-colors">
              <input
                type="checkbox"
                checked={revokeSuperseded}
                onChange={(e) => onRevokeSupersededChange(e.target.checked)}
                className="w-4 h-4 rounded border-border bg-bg-tertiary text-accent-warning focus:ring-accent-warning-op50"
              />
              <div>
                <p className="text-sm text-accent-warning font-medium">
                  {t('acme.revokeExistingSuperseded', { count: acmeSettings.superseded_count })}
                </p>
                <p className="text-xs text-text-secondary">{t('acme.revokeExistingSupersededDesc')}</p>
              </div>
            </label>
          )}
        </div>
      </CompactSection>

      <CompactSection title={t('acme.termsOfService')} icon={FileText}>
        <div className="space-y-2">
          {tosExists && savedPreview ? (
            <div className="rounded-lg border border-border bg-bg-tertiary p-3 max-h-52 overflow-y-auto">
              {tos.title && <p className="text-sm font-semibold text-text-primary mb-2">{tos.title}</p>}
              <div className="text-xs text-text-secondary [&>p]:mb-2 last:[&>p]:mb-0" dangerouslySetInnerHTML={{ __html: savedPreview }} />
            </div>
          ) : (
            <p className="text-xs text-text-tertiary">{t('acme.termsOfServiceHelper')}</p>
          )}
          {canWrite && (
            <Button type="button" variant="ghost" size="sm" onClick={handleOpenEdit}>
              <PencilSimple size={14} />
              {t('common.edit')}
            </Button>
          )}
        </div>
      </CompactSection>

      <CompactSection title={t('acme.endpoints')} icon={Lightning}>
        <CompactGrid columns={1}>
          <CompactField 
            autoIcon="environment"
            label={t('acme.directory')} 
            value={`${window.location.origin}/acme/directory`}
            mono
            copyable
          />
          {(acmeSettings.terms_of_service?.title || acmeSettings.terms_of_service?.body) && (
            <CompactField 
              label={t('acme.termsOfServiceUrl')}
              value={`${window.location.origin}/acme/terms`}
              mono
              copyable
            />
          )}
        </CompactGrid>
        <p className="text-xs text-text-tertiary mt-2">
          {t('acme.certbotUsage')} <code className="bg-bg-tertiary px-1 rounded">--server {window.location.origin}/acme/directory</code>
        </p>
      </CompactSection>

      {canWrite && (
        <div className="flex gap-2 pt-3 border-t border-border">
          <Button type="button" onClick={onSaveConfig} disabled={saving}>
            <FloppyDisk size={14} />
            {saving ? t('common.saving') : t('common.saveConfiguration')}
          </Button>
        </div>
      )}

      {/* Terms of Service edit modal */}
      <Modal open={editOpen} onClose={() => setEditOpen(false)} title={t('acme.termsOfService')} size="md">
        <div className="p-4 space-y-4">
          <Input
            name="tosTitle"
            value={editTitle}
            onChange={(e) => setEditTitle(e.target.value)}
            placeholder={t('acme.termsOfServiceTitlePlaceholder')}
          />
          <textarea
            value={editBody}
            onChange={(e) => setEditBody(e.target.value)}
            placeholder={t('acme.termsOfServiceBodyPlaceholder')}
            rows={10}
            className="w-full rounded-lg border border-border bg-bg-tertiary px-3 py-2 text-sm text-text-primary placeholder:text-text-tertiary focus:border-accent-primary focus:outline-none focus:ring-1 focus:ring-accent-primary-op50 resize-y"
          />
          <p className="text-xs text-text-tertiary">{t('acme.termsOfServiceHelper')}</p>
          {editPreview && (
            <div className="rounded-lg border border-border bg-bg-tertiary p-3">
              <p className="text-xs text-text-tertiary mb-2">{t('acme.termsOfServicePreview')}</p>
              <div className="text-xs text-text-secondary [&>p]:mb-2 last:[&>p]:mb-0" dangerouslySetInnerHTML={{ __html: editPreview }} />
            </div>
          )}
          <div className="flex justify-end gap-2 pt-4 border-t border-border">
            <Button type="button" variant="secondary" onClick={() => setEditOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button type="button" onClick={handleSaveEdit}>
              {t('common.save')}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  )
}
