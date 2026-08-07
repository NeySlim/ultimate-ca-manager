import { useTranslation } from 'react-i18next'
import { publicBaseUrl } from '../../lib/utils'
import { FloppyDisk, Globe, ArrowsClockwise, Lightning, FileText, PencilSimple, Stack } from '@phosphor-icons/react'
import { ToggleSwitch } from '../../components/ui/ToggleSwitch'
import { Select, Button, HelpCard, CompactSection, CompactGrid, CompactField, Input, Modal } from '../../components'
import { useState, useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkBreaks from 'remark-breaks'
import remarkGfm from 'remark-gfm'
import { MARKDOWN_ELEMENT_CLASSES } from '../../lib/ui'
import ProfilesEditor from './ProfilesEditor'

/** Render a markdown ToS preview.
 *
 * This used to be a hand-rolled regex sanitizer feeding dangerouslySetInnerHTML.
 * It escaped < > & but not double quotes, and never validated link schemes, so
 * admin-supplied ToS text could break out of an attribute or inject
 * `[x](javascript:...)` — stored XSS against any operator viewing the page.
 * ReactMarkdown (already used elsewhere in the app) escapes text nodes and
 * builds real React elements, so no raw HTML is ever interpolated; urlTransform
 * additionally pins hrefs to http/https/mailto.
 *
 * remark-gfm and remark-breaks preserve what the old sanitizer did beyond
 * CommonMark: bare URLs autolink and single newlines render as hard breaks,
 * so hard-wrapped ToS text keeps its line structure.
 */
export function TosPreview({ body }) {
  if (!body?.trim()) return null
  return (
    <div className={MARKDOWN_ELEMENT_CLASSES}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkBreaks]}
        urlTransform={(url) => {
          try {
            const parsed = new URL(url, window.location.origin)
            return ['http:', 'https:', 'mailto:'].includes(parsed.protocol) ? url : ''
          } catch {
            return ''
          }
        }}
        components={{
          // A link whose URL was rejected by urlTransform arrives with an
          // empty href; render it as plain text instead of an <a href="">
          // self-link that would open a copy of the console in a new tab.
          a: ({ node, href, children, ...props }) =>
            href ? (
              <a {...props} href={href} target="_blank" rel="noopener noreferrer">
                {children}
              </a>
            ) : (
              <span>{children}</span>
            ),
          // The old renderer could not emit images and the field does not
          // advertise them; a remote image would beacon to its host from
          // every operator's browser. Show the alt text instead.
          img: ({ alt }) => (alt ? <span>{alt}</span> : null),
        }}
      >
        {body}
      </ReactMarkdown>
    </div>
  )
}

export default function ConfigTab({ acmeSettings, cas, updateSetting, onSaveConfig, saving, revokeSuperseded, onRevokeSupersededChange, onToggleRevokeOnRenewal, canWrite }) {
  const { t } = useTranslation()
  const [editOpen, setEditOpen] = useState(false)
  const [editTitle, setEditTitle] = useState(acmeSettings.terms_of_service?.title || '')
  const [editBody, setEditBody] = useState(acmeSettings.terms_of_service?.body || '')

  const tos = acmeSettings.terms_of_service
  const tosExists = tos?.title || tos?.body
  const acmePublicBase = publicBaseUrl(acmeSettings.acme_public_base_url, '/acme')

  // Preview of saved ToS (from props)
  const savedPreview = useMemo(() => Boolean(tos?.body?.trim()), [tos?.body])

  // Preview inside edit modal
  const editPreview = useMemo(() => Boolean(editBody?.trim()), [editBody])

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

      <CompactSection title={t('acme.profiles')} icon={Stack}>
        <div className="space-y-3">
          <p className="text-xs text-text-secondary">{t('acme.profilesDesc')}</p>
          <ProfilesEditor
            value={acmeSettings.profiles || {}}
            onChange={(profiles) => updateSetting('profiles', profiles)}
            disabled={!canWrite}
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

      <CompactSection title={t('acme.caaSection')} icon={ArrowsClockwise}>
        <div className="space-y-2">
          <Input
            label={t('acme.caaIdentifiers')}
            value={acmeSettings.caa_identifiers || ''}
            onChange={(e) => updateSetting('caa_identifiers', e.target.value)}
            placeholder="ca.example.com, pki.example.com"
            helperText={t('acme.caaIdentifiersHelp')}
            disabled={!canWrite}
          />
          <ToggleSwitch
            checked={acmeSettings.caa_enforce || false}
            onChange={(val) => updateSetting('caa_enforce', val)}
            disabled={!canWrite}
            label={t('acme.caaEnforce')}
            description={t('acme.caaEnforceDesc')}
          />
          {acmeSettings.caa_enforce && (
            <p className="text-xs text-amber-500">{t('acme.caaEnforceWarning')}</p>
          )}
        </div>
      </CompactSection>

      <CompactSection title={t('acme.dnsPersistSection')} icon={ArrowsClockwise}>
        <div className="space-y-2">
          <ToggleSwitch
            checked={acmeSettings.dns_persist_enabled || false}
            onChange={(val) => updateSetting('dns_persist_enabled', val)}
            disabled={!canWrite}
            label={t('acme.dnsPersistEnabled')}
            description={t('acme.dnsPersistEnabledDesc')}
          />
          {acmeSettings.dns_persist_enabled && (
            <>
              <p className="text-xs text-amber-500">{t('acme.dnsPersistWarning')}</p>
              <p className="text-xs text-text-tertiary">
                {t('acme.dnsPersistIssuerNote', { domains: (acmeSettings.dns_persist_issuer_domains || []).join(', ') || '—' })}
              </p>
            </>
          )}
        </div>
      </CompactSection>

      <CompactSection title={t('acme.termsOfService')} icon={FileText}>
        <div className="space-y-2">
          {tosExists && savedPreview ? (
            <div className="rounded-lg border border-border bg-bg-tertiary p-3 max-h-52 overflow-y-auto">
              {tos.title && <p className="text-sm font-semibold text-text-primary mb-2">{tos.title}</p>}
              <div className="text-xs text-text-secondary"><TosPreview body={tos?.body} /></div>
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
            value={`${acmePublicBase}/directory`}
            mono
            copyable
          />
          {(acmeSettings.terms_of_service?.title || acmeSettings.terms_of_service?.body) && (
            <CompactField 
              label={t('acme.termsOfServiceUrl')}
              value={`${acmePublicBase}/terms`}
              mono
              copyable
            />
          )}
        </CompactGrid>
        <p className="text-xs text-text-tertiary mt-2">
          {t('acme.certbotUsage')} <code className="bg-bg-tertiary px-1 rounded">--server {acmePublicBase}/directory</code>
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
              <div className="text-xs text-text-secondary"><TosPreview body={editBody} /></div>
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
