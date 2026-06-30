import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Plus, Trash, PencilSimple, Key, CheckCircle, Star, Globe, LockKey, X
} from '@phosphor-icons/react'
import { Button, Badge, Input, Select, CompactSection } from '../../components'

const EMPTY_FORM = {
  label: '',
  directory_url: '',
  email: '',
  account_key_algorithm: 'ES256',
  eab_kid: '',
  eab_hmac_key: '',
  is_default: false,
}

/**
 * Multi-CA account manager for the ACME client. Lists every external ACME
 * authority (Let's Encrypt, Actalis, ZeroSSL...) UCM can request certificates
 * from, and lets admins add/edit/remove them, set the default, and register.
 */
export default function CaAccountsManager({
  accounts = [],
  canWrite,
  canDelete,
  onCreate,
  onUpdate,
  onDelete,
  onSetDefault,
  onRegister,
}) {
  const { t } = useTranslation()
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [busy, setBusy] = useState(false)

  const openCreate = () => {
    setEditingId(null)
    setForm(EMPTY_FORM)
    setShowForm(true)
  }

  const openEdit = (acct) => {
    setEditingId(acct.id)
    setForm({
      label: acct.label || '',
      directory_url: acct.directory_url || '',
      email: acct.email || '',
      account_key_algorithm: acct.account_key_algorithm || 'ES256',
      eab_kid: acct.eab_kid || '',
      eab_hmac_key: '',
      is_default: !!acct.is_default,
    })
    setShowForm(true)
  }

  const closeForm = () => {
    setShowForm(false)
    setEditingId(null)
    setForm(EMPTY_FORM)
  }

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    try {
      if (editingId) {
        const payload = {
          label: form.label,
          email: form.email,
          account_key_algorithm: form.account_key_algorithm,
          eab_kid: form.eab_kid,
          is_default: form.is_default,
        }
        if (form.eab_hmac_key) payload.eab_hmac_key = form.eab_hmac_key
        await onUpdate(editingId, payload)
      } else {
        await onCreate({ ...form })
      }
      closeForm()
    } finally {
      setBusy(false)
    }
  }

  return (
    <CompactSection title={t('acme.certificateAuthorities')} icon={Globe}>
      <div className="space-y-3">
        <p className="text-xs text-text-tertiary">{t('acme.certificateAuthoritiesDesc')}</p>

        {canWrite && !showForm && (
          <Button type="button" size="sm" onClick={openCreate}>
            <Plus size={14} />
            {t('acme.addCertificateAuthority')}
          </Button>
        )}

        {/* Account list */}
        {accounts.length === 0 ? (
          <p className="text-xs text-text-tertiary py-3 text-center">{t('acme.noCaAccounts')}</p>
        ) : (
          <div className="space-y-2">
            {accounts.map((acct) => (
              <div key={acct.id} className="p-3 bg-tertiary-op50 rounded-lg border border-border-op50">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-medium text-text-primary truncate">{acct.label}</span>
                      {acct.is_default && (
                        <Badge variant="success" size="sm"><Star size={10} weight="fill" /> {t('common.default')}</Badge>
                      )}
                      {acct.environment && acct.environment !== 'custom' && (
                        <Badge variant="secondary" size="sm">{acct.environment}</Badge>
                      )}
                      {acct.is_registered
                        ? <Badge variant="success" size="sm"><CheckCircle size={10} weight="fill" /> {t('acme.registered')}</Badge>
                        : <Badge variant="warning" size="sm">{t('acme.notRegistered')}</Badge>}
                      {acct.eab_kid && (
                        <Badge variant="outline" size="sm"><LockKey size={10} /> EAB</Badge>
                      )}
                    </div>
                    <p className="text-xs text-text-tertiary font-mono truncate mt-1" title={acct.directory_url}>
                      {acct.directory_url}
                    </p>
                    <p className="text-xs text-text-tertiary mt-0.5">{acct.email}</p>
                  </div>
                </div>
                {canWrite && (
                  <div className="flex flex-wrap gap-2 mt-2 pt-2 border-t border-border-op30">
                    {!acct.is_registered && (
                      <Button type="button" variant="secondary" size="sm" onClick={() => onRegister(acct.id, acct.email)}>
                        <Key size={12} /> {t('acme.registerAccount')}
                      </Button>
                    )}
                    {!acct.is_default && (
                      <Button type="button" variant="secondary" size="sm" onClick={() => onSetDefault(acct.id)}>
                        <Star size={12} /> {t('acme.setDefault')}
                      </Button>
                    )}
                    <Button type="button" variant="secondary" size="sm" onClick={() => openEdit(acct)}>
                      <PencilSimple size={12} /> {t('common.edit')}
                    </Button>
                    {canDelete && (
                      <Button type="button" variant="danger" size="sm" onClick={() => onDelete(acct.id)}>
                        <Trash size={12} /> {t('common.delete')}
                      </Button>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Create / edit form */}
        {showForm && (
          <form onSubmit={submit} className="p-3 bg-bg-secondary rounded-lg border border-border space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-text-primary">
                {editingId ? t('acme.editCertificateAuthority') : t('acme.addCertificateAuthority')}
              </p>
              <Button type="button" variant="ghost" size="sm" onClick={closeForm}>
                <X size={14} />
              </Button>
            </div>

            <Input
              label={t('acme.caLabel')}
              value={form.label}
              onChange={(e) => setForm(p => ({ ...p, label: e.target.value }))}
              placeholder="Actalis Production"
              required
            />

            <Input
              label={t('acme.directoryUrl')}
              type="url"
              value={form.directory_url}
              onChange={(e) => setForm(p => ({ ...p, directory_url: e.target.value }))}
              placeholder="https://acme-api.actalis.com/acme/directory"
              disabled={!!editingId}
              required
              helperText={editingId ? t('acme.directoryUrlImmutable') : t('acme.directoryUrlHelper')}
            />

            <Input
              label={t('acme.contactEmail')}
              type="email"
              value={form.email}
              onChange={(e) => setForm(p => ({ ...p, email: e.target.value }))}
              required
            />

            <Select
              label={t('acme.accountKeyType')}
              value={form.account_key_algorithm}
              onChange={(val) => setForm(p => ({ ...p, account_key_algorithm: val }))}
              options={[
                { value: 'ES256', label: 'ECDSA P-256 (ES256)' },
                { value: 'ES384', label: 'ECDSA P-384 (ES384)' },
                { value: 'RS256', label: 'RSA 2048 (RS256)' },
              ]}
            />

            <Input
              label={t('acme.eabKid')}
              value={form.eab_kid}
              onChange={(e) => setForm(p => ({ ...p, eab_kid: e.target.value }))}
              placeholder="key-id-from-ca"
              helperText={t('acme.eabKidHelper')}
            />

            <Input
              label={t('acme.eabHmacKey')}
              type="password"
              value={form.eab_hmac_key}
              onChange={(e) => setForm(p => ({ ...p, eab_hmac_key: e.target.value }))}
              placeholder={editingId ? t('acme.eabHmacKeyKeepPlaceholder') : t('acme.eabHmacKeyPlaceholder')}
              helperText={t('acme.eabHmacKeyHelper')}
            />

            <label className="flex items-center gap-2 text-sm text-text-secondary">
              <input
                type="checkbox"
                checked={form.is_default}
                onChange={(e) => setForm(p => ({ ...p, is_default: e.target.checked }))}
              />
              {t('acme.useAsDefault')}
            </label>

            <div className="flex justify-end gap-2 pt-2 border-t border-border">
              <Button type="button" variant="secondary" onClick={closeForm}>{t('common.cancel')}</Button>
              <Button type="submit" disabled={busy}>
                {editingId ? t('common.save') : t('common.add')}
              </Button>
            </div>
          </form>
        )}
      </div>
    </CompactSection>
  )
}
