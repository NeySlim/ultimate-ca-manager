import { useTranslation } from 'react-i18next'
import { publicBaseUrl } from '../../lib/utils'
import { useState, useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkBreaks from 'remark-breaks'
import remarkGfm from 'remark-gfm'
import { Btn, SettingsView } from '../../components/atelier'
import { Input, Textarea, Modal } from '../../components/atelier/Form'
import { MARKDOWN_COMPONENTS } from '../../components/atelier/markdown'
import ProfilesEditor from './ProfilesEditor'
import { pickerCas, unlistedPickerCas } from '../../lib/caSelection'
import { Field, Notice } from '../protocols/atelierParts'

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
    <div className="event-detail">
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
          ...MARKDOWN_COMPONENTS,
          // A link whose URL was rejected by urlTransform arrives with an
          // empty href; render it as plain text instead of an <a href="">
          // self-link that would open a copy of the console in a new tab.
          a: ({ node, href, children, ...props }) =>
            href ? (
              <a {...props} className="text-link" href={href} target="_blank" rel="noopener noreferrer">
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

// The ACME server settings drawn as the mockup's settingsView(): the parent holds the draft
// (acmeSettings) and the saved settings (saved); every change comes back through updateSetting.
const FIELDS = ['enabled', 'issuing_ca_id', 'default_profile', 'default_digest', 'revoke_on_renewal', 'allow_private_ips',
  'caa_identifiers', 'caa_enforce', 'dns_persist_enabled']
const norm = (k, v) => (k === 'allow_private_ips' ? v ?? true : ['enabled', 'revoke_on_renewal', 'caa_enforce', 'dns_persist_enabled'].includes(k) ? !!v
  : k === 'default_digest' ? v || 'sha256' : v ?? '')

export default function ConfigTab({ acmeSettings, saved = acmeSettings, savedProfiles = {}, cas, templates = [], updateSetting, onSaveConfig, onReset, saving,
  revokeSuperseded, onRevokeSupersededChange, onToggleRevokeOnRenewal, canWrite }) {
  const { t } = useTranslation()
  const [editOpen, setEditOpen] = useState(false)
  const [editTitle, setEditTitle] = useState(acmeSettings.terms_of_service?.title || '')
  const [editBody, setEditBody] = useState(acmeSettings.terms_of_service?.body || '')
  const tos = acmeSettings.terms_of_service
  const tosExists = tos?.title || tos?.body
  const acmePublicBase = publicBaseUrl(acmeSettings.acme_public_base_url, '/acme')
  const editPreview = useMemo(() => Boolean(editBody?.trim()), [editBody])
  const off = !canWrite

  const handleOpenEdit = () => {
    setEditTitle(tos?.title || '')
    setEditBody(tos?.body || '')
    setEditOpen(true)
  }
  const handleSaveEdit = () => {
    updateSetting('terms_of_service', { title: editTitle, body: editBody })
    setEditOpen(false)
  }

  const onProfiles = (profiles) => {
    updateSetting('profiles', profiles)
    // A renamed default follows its new name; a removed one is dropped
    const previous = acmeSettings.profiles || {}
    const current = acmeSettings.default_profile
    // A name emptied while typing is not a removal yet
    if (current && !(current in profiles) && !('' in profiles)) {
      const added = Object.keys(profiles).filter(name => !(name in previous))
      const renamed = added.length === 1 && Object.keys(profiles).length === Object.keys(previous).length
      updateSetting('default_profile', renamed ? added[0] : '')
    }
  }

  const changed = [
    ...FIELDS.filter((k) => String(norm(k, acmeSettings[k])) !== String(norm(k, saved[k]))),
    ...(JSON.stringify(acmeSettings.profiles || {}) !== JSON.stringify(saved.profiles || {}) ? ['profiles'] : []),
    ...(JSON.stringify(acmeSettings.terms_of_service || {}) !== JSON.stringify(saved.terms_of_service || {}) ? ['terms_of_service'] : []),
  ]
  const values = Object.fromEntries(FIELDS.map((k) => [k, norm(k, acmeSettings[k])]))
  values.issuing_ca_id = acmeSettings.issuing_ca_id != null && acmeSettings.issuing_ca_id !== '' ? String(acmeSettings.issuing_ca_id) : ''
  const onChange = (key, value) => {
    if (key === 'revoke_on_renewal') onToggleRevokeOnRenewal(value)
    else if (key === 'issuing_ca_id') updateSetting(key, value ? parseInt(value, 10) : null)
    else updateSetting(key, value)
  }
  const unlisted = unlistedPickerCas(cas, acmeSettings.issuing_ca_id)

  const sections = [
    {
      id: 'server', label: t('acme.acmeServer'), icon: 'refresh', desc: t('acme.aboutAcmeDesc'),
      groups: [{ legend: t('acme.acmeServer'), fields: [
        { key: 'enabled', label: t('acme.enableAcmeServer'), hint: t('acme.enableAcmeServerDesc'), checkbox: true, disabled: off },
        { key: 'issuing_ca_id', label: t('acme.defaultIssuingCA'), disabled: !acmeSettings.enabled || off,
          hint: unlisted > 0 ? t('cas.notListedForSigning', { count: unlisted }) : undefined,
          options: [['', t('common.acmeSelectCA')], ...pickerCas(cas, acmeSettings.issuing_ca_id).map(ca => [ca.id.toString(), ca.name || ca.common_name])] },
      ] }],
    },
    {
      id: 'profiles', label: t('acme.profiles'), icon: 'template', desc: t('acme.profilesDesc'),
      extraKeys: [['profiles', t('acme.profiles')], ['default_profile', t('acme.defaultProfile')], ['default_digest', t('acme.defaultDigest')]],
      groups: [],
      children: (
        <fieldset className="settings-group">
          <legend>{t('acme.profiles')}</legend>
          <ProfilesEditor value={acmeSettings.profiles || {}} saved={savedProfiles} onChange={onProfiles} disabled={off} templates={templates} />
          <p className="muted small">{t('acme.profileTemplateHelp')}</p>
          <div className="settings-grid">
            <Field label={t('acme.defaultProfile')} hint={t('acme.defaultProfileDesc')} id="acme-default-profile">
              {(p) => (
                <select {...p} value={acmeSettings.default_profile || ''} disabled={off || undefined} onChange={(e) => updateSetting('default_profile', e.target.value)}>
                  <option value="">{t('acme.defaultProfileNone')}</option>
                  {Object.keys(acmeSettings.profiles || {}).map(name => <option key={name} value={name}>{name}</option>)}
                </select>
              )}
            </Field>
            <Field label={t('acme.defaultDigest')} hint={t('acme.defaultDigestDesc')} id="acme-default-digest">
              {(p) => (
                <select {...p} value={acmeSettings.default_digest || 'sha256'} disabled={off || undefined} onChange={(e) => updateSetting('default_digest', e.target.value)}>
                  <option value="sha256">SHA-256</option><option value="sha384">SHA-384</option><option value="sha512">SHA-512</option>
                </select>
              )}
            </Field>
          </div>
        </fieldset>
      ),
    },
    {
      id: 'renewal', label: t('acme.renewalPolicy'), icon: 'refresh', desc: t('acme.revokeOnRenewalDesc'),
      groups: [{ legend: t('acme.renewalPolicy'), fields: [
        { key: 'revoke_on_renewal', label: t('acme.revokeOnRenewal'), checkbox: true, disabled: off },
      ] }],
      children: !acmeSettings.revoke_on_renewal && acmeSettings.superseded_count > 0 && (
        <div className="field full">
          <label className="checkbox-line">
            <input type="checkbox" checked={!!revokeSuperseded} disabled={off || undefined} aria-describedby="acme-revoke-superseded-hint"
              onChange={(e) => onRevokeSupersededChange(e.target.checked)} />
            {t('acme.revokeExistingSuperseded', { count: acmeSettings.superseded_count })}
          </label>
          <small id="acme-revoke-superseded-hint">{t('acme.revokeExistingSupersededDesc')}</small>
        </div>
      ),
    },
    {
      id: 'targets', label: t('acme.challengeTargets'), icon: 'globe', desc: t('acme.allowPrivateIpsDesc'),
      groups: [{ legend: t('acme.challengeTargets'), fields: [
        { key: 'allow_private_ips', label: t('acme.allowPrivateIps'), checkbox: true, disabled: off },
      ] }],
    },
    {
      id: 'caa', label: t('acme.caaSection'), icon: 'policy', desc: t('acme.caaIdentifiersHelp'),
      groups: [{ legend: t('acme.caaSection'), fields: [
        { key: 'caa_identifiers', label: t('acme.caaIdentifiers'), placeholder: 'ca.example.com, pki.example.com', wide: true, disabled: off },
        { key: 'caa_enforce', label: t('acme.caaEnforce'), hint: t('acme.caaEnforceDesc'), checkbox: true, disabled: off },
      ] }],
      children: acmeSettings.caa_enforce && <Notice tone="warn">{t('acme.caaEnforceWarning')}</Notice>,
    },
    {
      id: 'persist', label: t('acme.dnsPersistSection'), icon: 'globe', desc: t('acme.dnsPersistEnabledDesc'),
      groups: [{ legend: t('acme.dnsPersistSection'), fields: [
        { key: 'dns_persist_enabled', label: t('acme.dnsPersistEnabled'), checkbox: true, disabled: off },
      ] }],
      children: acmeSettings.dns_persist_enabled && (
        <>
          <Notice tone="warn">{t('acme.dnsPersistWarning')}</Notice>
          <p className="muted small">{t('acme.dnsPersistIssuerNote', { domains: (acmeSettings.dns_persist_issuer_domains || []).join(', ') || '—' })}</p>
        </>
      ),
    },
    {
      id: 'tos', label: t('acme.termsOfService'), icon: 'file', desc: t('acme.termsOfServiceHelper'),
      extraKeys: [['terms_of_service', t('acme.termsOfService')]],
      groups: [],
      children: (
        <fieldset className="settings-group">
          <legend>{t('acme.termsOfService')}</legend>
          {tosExists && tos?.body?.trim() ? (
            <div className="summary tos-preview">
              {tos.title && <strong>{tos.title}</strong>}
              <TosPreview body={tos?.body} />
            </div>
          ) : <p className="muted small">{t('acme.termsOfServiceHelper')}</p>}
          {canWrite && <div className="copy-url"><Btn icon="settings" write onClick={handleOpenEdit}>{t('common.edit')}</Btn></div>}
        </fieldset>
      ),
    },
    {
      id: 'endpoints', label: t('acme.endpoints'), icon: 'link', desc: t('acme.certbotUsage'),
      groups: [{ legend: t('acme.endpoints'), fields: [
        { key: 'directory', label: t('acme.directory'), readonly: `${acmePublicBase}/directory` },
        ...(tosExists ? [{ key: 'terms', label: t('acme.termsOfServiceUrl'), readonly: `${acmePublicBase}/terms` }] : []),
      ] }],
      children: <pre className="code-preview">{`--server ${acmePublicBase}/directory`}</pre>,
    },
  ]

  return (
    <>
      <SettingsView sections={sections} values={values} changed={changed} onChange={onChange}
        onSave={canWrite ? onSaveConfig : undefined} onReset={onReset} saving={saving} tocLabel={t('protocols.sectionsOf', { name: t('acme.acmeServer') })} />
      {/* Terms of Service edit modal */}
      <Modal open={editOpen} onClose={() => setEditOpen(false)} title={t('acme.termsOfService')} testId="acme-tos-dialog">
        <form noValidate onSubmit={(e) => { e.preventDefault(); handleSaveEdit() }}>
          <div className="form-fields">
            <Input id="acme-tos-title" name="tosTitle" label={t('acme.termsOfServiceTitle')} full value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)} placeholder={t('acme.termsOfServiceTitlePlaceholder')} data-autofocus="" />
            <Textarea id="acme-tos-body" label={t('acme.termsOfServiceBody')} rows={10} value={editBody} onChange={(e) => setEditBody(e.target.value)}
              placeholder={t('acme.termsOfServiceBodyPlaceholder')} helperText={t('acme.termsOfServiceHelper')} />
          </div>
          {editPreview && (
            <section className="review-summary" style={{ marginTop: 18 }}>
              <h3 className="section-title">{t('acme.termsOfServicePreview')}</h3>
              <TosPreview body={editBody} />
            </section>
          )}
          <div className="modal-actions">
            <button type="button" className="btn" data-action="close-modal" onClick={() => setEditOpen(false)}>{t('common.cancel')}</button>
            <button type="submit" className="btn primary">{t('common.save')}</button>
          </div>
        </form>
      </Modal>
    </>
  )
}
