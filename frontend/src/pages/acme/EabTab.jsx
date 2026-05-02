import { useState, useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus, Trash, LockKey, Copy, Clock, Warning } from '@phosphor-icons/react'
import { ToggleSwitch } from '../../components/ui/ToggleSwitch'
import { Button, Badge, Card, Input, Select, Modal } from '../../components'
import { acmeService } from '../../services'
import { useNotification } from '../../contexts'
import { useClipboard } from '../../hooks'
import { formatDate } from '../../lib/utils'

export default function EabTab({ eabRequired, onToggleEabRequired, showCreateModal, onCloseCreateModal, canWrite, canDelete }) {
  const { t } = useTranslation()
  const { showSuccess, showError, showConfirm } = useNotification()
  const { copy } = useClipboard()

  const [eabCredentials, setEabCredentials] = useState([])
  const [eabFilterStatus, setEabFilterStatus] = useState('')
  const [showLocalCreate, setShowLocalCreate] = useState(false)
  const [newEabSecret, setNewEabSecret] = useState(null)
  const [eabLabel, setEabLabel] = useState('')
  const [eabExpiresInDays, setEabExpiresInDays] = useState('')

  useEffect(() => {
    acmeService.listEabCredentials()
      .then(res => setEabCredentials(res.data || []))
      .catch(() => {})
  }, [])

  const filteredEabCredentials = useMemo(() => {
    if (!eabFilterStatus) return eabCredentials
    return eabCredentials.filter(c => c.status === eabFilterStatus)
  }, [eabCredentials, eabFilterStatus])

  const handleCreateEabCredential = async () => {
    try {
      const payload = { label: eabLabel || null }
      const days = parseInt(eabExpiresInDays, 10)
      if (!Number.isNaN(days) && days > 0) payload.expires_in_days = days

      const res = await acmeService.createEabCredential(payload)
      const created = res.data || res
      setNewEabSecret(created)
      setShowLocalCreate(false)
      onCloseCreateModal()
      setEabLabel('')
      setEabExpiresInDays('')
      const list = await acmeService.listEabCredentials()
      setEabCredentials(list.data || [])
    } catch (error) {
      showError(error.message || t('acme.eab.createFailed'))
    }
  }

  const handleRevokeEabCredential = async (cred) => {
    const confirmed = await showConfirm(
      t('acme.eab.confirmRevoke', { kid: cred.kid }),
      {
        title: t('acme.eab.revokeTitle'),
        confirmText: t('acme.eab.revoke'),
        variant: 'danger'
      }
    )
    if (!confirmed) return
    try {
      await acmeService.revokeEabCredential(cred.id)
      showSuccess(t('acme.eab.revokedSuccess'))
      const list = await acmeService.listEabCredentials()
      setEabCredentials(list.data || [])
    } catch (error) {
      showError(error.message || t('acme.eab.revokeFailed'))
    }
  }

  const isCreateOpen = showCreateModal || showLocalCreate

  return (
    <>
      <div className="space-y-4">
        <Card>
          <div className="p-4 flex items-center justify-between gap-4">
            <div className="flex items-start gap-3 min-w-0">
              <div className="w-10 h-10 rounded-lg icon-bg-violet flex items-center justify-center shrink-0">
                <LockKey size={20} weight="duotone" />
              </div>
              <div className="min-w-0">
                <div className="font-semibold">{t('acme.eab.requiredTitle')}</div>
                <div className="text-sm text-text-tertiary mt-1">
                  {t('acme.eab.requiredDescription')}
                </div>
              </div>
            </div>
            <ToggleSwitch
              checked={eabRequired}
              onChange={onToggleEabRequired}
              disabled={!canWrite}
            />
          </div>
        </Card>

        <Card>
          <div className="p-4 border-b border-border flex items-center gap-3">
            <Select
              value={eabFilterStatus}
              onChange={setEabFilterStatus}
              options={[
                { value: '', label: t('acme.eab.allStatuses') },
                { value: 'active', label: t('acme.eab.statusActive') },
                { value: 'used', label: t('acme.eab.statusUsed') },
                { value: 'revoked', label: t('acme.eab.statusRevoked') }
              ]}
              className="w-44"
            />
            <span className="text-sm text-text-tertiary">
              {t('acme.eab.totalCount', { count: filteredEabCredentials.length })}
            </span>
          </div>
          {filteredEabCredentials.length === 0 ? (
            <div className="p-8 text-center">
              <LockKey size={36} className="mx-auto mb-3 text-text-tertiary" weight="duotone" />
              <div className="font-medium">{t('acme.eab.empty')}</div>
              <div className="text-sm text-text-tertiary mt-1">{t('acme.eab.emptyDesc')}</div>
              {canWrite && (
                <Button type="button" className="mt-4" onClick={() => setShowLocalCreate(true)}>
                  <Plus size={14} />
                  {t('acme.eab.new')}
                </Button>
              )}
            </div>
          ) : (
            <div className="divide-y divide-border">
              {filteredEabCredentials.map(cred => (
                <div key={cred.id} className="p-4 flex items-center justify-between gap-3 hover:bg-tertiary-op40">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium truncate">{cred.label || t('acme.eab.unlabeled')}</span>
                      <Badge variant={
                        cred.status === 'active' ? 'success' :
                        cred.status === 'used' ? 'info' :
                        cred.status === 'revoked' ? 'danger' :
                        'default'
                      }>
                        {t(`acme.eab.status${cred.status.charAt(0).toUpperCase() + cred.status.slice(1)}`)}
                      </Badge>
                      {cred.expires_at && (
                        <Badge variant="warning" className="text-xs">
                          <Clock size={12} /> {formatDate(cred.expires_at)}
                        </Badge>
                      )}
                    </div>
                    <div className="mt-1 flex items-center gap-2 text-xs text-text-tertiary font-mono break-all">
                      <span>kid:</span>
                      <span className="select-all">{cred.kid}</span>
                      <button
                        type="button"
                        className="text-accent-primary hover:underline"
                        onClick={() => { copy(cred.kid); showSuccess(t('acme.eab.kidCopied')) }}
                        title={t('common.copy')}
                      >
                        <Copy size={12} />
                      </button>
                    </div>
                    <div className="mt-1 text-xs text-text-tertiary">
                      {t('acme.eab.created')}: {formatDate(cred.created_at)}
                      {cred.used_at && (
                        <> · {t('acme.eab.usedAt')}: {formatDate(cred.used_at)}</>
                      )}
                      {cred.used_by_account_id && (
                        <> · {t('acme.eab.boundTo')}: <span className="font-mono">{cred.used_by_account_id.slice(0, 16)}…</span></>
                      )}
                      {cred.revoked_at && (
                        <> · {t('acme.eab.revokedAt')}: {formatDate(cred.revoked_at)}</>
                      )}
                    </div>
                  </div>
                  {canDelete && cred.status === 'active' && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => handleRevokeEabCredential(cred)}
                      title={t('acme.eab.revoke')}
                    >
                      <Trash size={14} />
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* Create EAB Credential Modal */}
      <Modal
        open={isCreateOpen}
        onClose={() => { setShowLocalCreate(false); onCloseCreateModal() }}
        title={t('acme.eab.newTitle')}
      >
        <div className="p-4 space-y-4">
          <p className="text-sm text-text-tertiary">
            {t('acme.eab.newDescription')}
          </p>
          <Input
            label={t('acme.eab.label')}
            placeholder={t('acme.eab.labelPlaceholder')}
            value={eabLabel}
            onChange={(e) => setEabLabel(e.target.value)}
            maxLength={255}
          />
          <Input
            label={t('acme.eab.expiresInDays')}
            type="number"
            placeholder={t('acme.eab.expiresPlaceholder')}
            value={eabExpiresInDays}
            onChange={(e) => setEabExpiresInDays(e.target.value)}
            min={1}
            helperText={t('acme.eab.expiresHelp')}
          />
          <div className="flex justify-end gap-2 pt-2 border-t border-border">
            <Button type="button" variant="secondary" onClick={() => { setShowLocalCreate(false); onCloseCreateModal() }}>
              {t('common.cancel')}
            </Button>
            <Button type="button" onClick={handleCreateEabCredential}>
              {t('acme.eab.generate')}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Show EAB Secret Once Modal */}
      <Modal
        open={!!newEabSecret}
        onClose={() => setNewEabSecret(null)}
        title={t('acme.eab.secretTitle')}
        size="md"
      >
        {newEabSecret && (
          <div className="p-4 space-y-4">
            <div className="rounded-lg border border-yellow-500/40 bg-yellow-500/10 p-3 flex gap-2">
              <Warning size={20} className="text-yellow-500 shrink-0 mt-0.5" weight="duotone" />
              <div className="text-sm">
                <div className="font-semibold">{t('acme.eab.secretWarningTitle')}</div>
                <div className="text-text-tertiary mt-1">{t('acme.eab.secretWarning')}</div>
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">{t('acme.eab.kid')}</label>
              <div className="flex items-center gap-2">
                <code className="flex-1 px-3 py-2 rounded bg-bg-tertiary font-mono text-sm break-all">{newEabSecret.kid}</code>
                <Button type="button" variant="secondary" size="sm" onClick={() => { copy(newEabSecret.kid); showSuccess(t('acme.eab.kidCopied')) }}>
                  <Copy size={14} />
                </Button>
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">{t('acme.eab.hmacKey')}</label>
              <div className="flex items-center gap-2">
                <code className="flex-1 px-3 py-2 rounded bg-bg-tertiary font-mono text-sm break-all">{newEabSecret.hmac_key}</code>
                <Button type="button" variant="secondary" size="sm" onClick={() => { copy(newEabSecret.hmac_key); showSuccess(t('acme.eab.hmacCopied')) }}>
                  <Copy size={14} />
                </Button>
              </div>
              <p className="text-xs text-text-tertiary mt-1">{t('acme.eab.hmacFormat')}</p>
            </div>
            <div className="flex justify-end pt-2 border-t border-border">
              <Button type="button" onClick={() => setNewEabSecret(null)}>
                {t('acme.eab.secretConfirm')}
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </>
  )
}
