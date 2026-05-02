/**
 * CAs Page — Create CA modal (self-contained with own state + effects)
 *
 * Props:
 *   open       — boolean, whether modal is open
 *   onClose    — called when modal should close
 *   cas        — array of existing CAs (for parent CA select dropdown)
 *   onSuccess  — called after CA is successfully created
 */
import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { CaretRight, CaretDown } from '@phosphor-icons/react'
import { Modal, Input, Select, Button } from '../../components'
import { casService, hsmService } from '../../services'
import { useNotification } from '../../contexts'
import { useWebSocket } from '../../hooks'
import { extractData, cn } from '../../lib/utils'

export function CreateCAModal({ open, onClose, cas, onSuccess }) {
  const { t } = useTranslation()
  const { showSuccess, showError } = useNotification()
  const { muteToasts } = useWebSocket()

  const [createFormType, setCreateFormType] = useState('root')
  const [createFormParentCAId, setCreateFormParentCAId] = useState(null)
  const [createFormKeyAlgo, setCreateFormKeyAlgo] = useState('RSA')
  const [createFormKeySize, setCreateFormKeySize] = useState('2048')
  const [createFormValidity, setCreateFormValidity] = useState('10')
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [createFormPathLength, setCreateFormPathLength] = useState('')
  const [createFormOcspMustStaple, setCreateFormOcspMustStaple] = useState(false)

  // HSM key storage state
  const [createFormKeyStorage, setCreateFormKeyStorage] = useState('local') // 'local' | 'hsm'
  const [createFormHsmProviderId, setCreateFormHsmProviderId] = useState('')
  const [createFormHsmKeyMode, setCreateFormHsmKeyMode] = useState('generate') // 'generate' | 'existing'
  const [createFormHsmKeyLabel, setCreateFormHsmKeyLabel] = useState('')
  const [createFormHsmKeyAlgorithm, setCreateFormHsmKeyAlgorithm] = useState('RSA-2048')
  const [createFormHsmKeyId, setCreateFormHsmKeyId] = useState('')
  const [hsmProviders, setHsmProviders] = useState([])
  const [hsmKeys, setHsmKeys] = useState([])
  const [hsmLoading, setHsmLoading] = useState(false)

  // Load HSM providers when modal opens
  useEffect(() => {
    if (!open) return
    let cancelled = false
    setHsmLoading(true)
    hsmService.getProviders()
      .then(res => {
        if (cancelled) return
        const list = extractData(res) || []
        setHsmProviders(list.filter(p => p.enabled))
      })
      .catch(() => { if (!cancelled) setHsmProviders([]) })
      .finally(() => { if (!cancelled) setHsmLoading(false) })
    return () => { cancelled = true }
  }, [open])

  // Load HSM signing keys when provider selected and "use existing" mode active
  useEffect(() => {
    if (createFormKeyStorage !== 'hsm' || createFormHsmKeyMode !== 'existing' || !createFormHsmProviderId) {
      setHsmKeys([])
      return
    }
    let cancelled = false
    hsmService.getSigningKeys({ providerId: parseInt(createFormHsmProviderId, 10), unused: true })
      .then(res => {
        if (cancelled) return
        setHsmKeys(extractData(res) || [])
      })
      .catch(() => { if (!cancelled) setHsmKeys([]) })
    return () => { cancelled = true }
  }, [createFormKeyStorage, createFormHsmKeyMode, createFormHsmProviderId])

  // Reset HSM form state when modal closes
  useEffect(() => {
    if (open) return
    setCreateFormKeyStorage('local')
    setCreateFormHsmProviderId('')
    setCreateFormHsmKeyMode('generate')
    setCreateFormHsmKeyLabel('')
    setCreateFormHsmKeyAlgorithm('RSA-2048')
    setCreateFormHsmKeyId('')
  }, [open])

  const handleCreateCA = async (e) => {
    e.preventDefault()
    const formData = new FormData(e.target)
    const data = {
      commonName: formData.get('commonName'),
      organization: formData.get('organization'),
      organizationalUnit: formData.get('organizationalUnit'),
      country: formData.get('country'),
      state: formData.get('state'),
      locality: formData.get('locality'),
      description: formData.get('description'),
      keyAlgo: createFormKeyAlgo,
      keySize: createFormKeyAlgo === 'ECDSA' ? createFormKeySize : parseInt(createFormKeySize),
      validityYears: parseInt(createFormValidity),
      type: createFormType,
      parentCAId: createFormType === 'intermediate' ? createFormParentCAId : null,
      ...(createFormPathLength !== '' && { pathLength: parseInt(createFormPathLength) }),
    }

    // HSM key storage — replaces local key fields
    if (createFormKeyStorage === 'hsm') {
      if (!createFormHsmProviderId) {
        showError(t('cas.create.hsmProviderRequired'))
        return
      }
      delete data.keyAlgo
      delete data.keySize
      if (createFormHsmKeyMode === 'generate') {
        const label = (createFormHsmKeyLabel || '').trim()
        if (!label) {
          showError(t('cas.create.hsmKeyLabelRequired'))
          return
        }
        if (!/^[a-zA-Z0-9_-]+$/.test(label)) {
          showError(t('cas.create.hsmKeyLabelInvalid'))
          return
        }
        data.hsmProviderId = parseInt(createFormHsmProviderId, 10)
        data.hsmKeyLabel = label
        data.hsmKeyAlgorithm = createFormHsmKeyAlgorithm
      } else {
        if (!createFormHsmKeyId) {
          showError(t('cas.create.hsmExistingKeyRequired'))
          return
        }
        data.hsmKeyId = parseInt(createFormHsmKeyId, 10)
      }
    }

    try {
      muteToasts()
      await casService.create(data)
      showSuccess(t('messages.success.create.ca'))
      onClose()
      onSuccess()
    } catch (error) {
      showError(error.message || t('cas.createFailed'))
    }
  }

  return (
    <Modal
      open={open}
      onOpenChange={onClose}
      title={t('common.createCA')}
      size="lg"
    >
      <form onSubmit={handleCreateCA} className="space-y-6 p-4">
        <div className="space-y-4">
          <h3 className="text-sm font-semibold text-text-primary">{t('cas.subjectInfo')}</h3>
          <Input name="commonName" label={t('common.commonName') + ' (CN)'} placeholder={t('cas.cnPlaceholder')} required />
          <div className="grid grid-cols-2 gap-4">
            <Input name="country" label={t('common.country') + ' (C)'} placeholder={t('common.countryPlaceholder')} maxLength={2} />
            <Input name="state" label={t('common.stateProvince') + ' (ST)'} placeholder={t('common.statePlaceholder')} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Input name="locality" label={t('cas.locality') + ' (L)'} placeholder={t('cas.localityPlaceholder')} />
            <Input name="organization" label={t('common.organization') + ' (O)'} placeholder={t('cas.orgPlaceholder')} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Input name="organizationalUnit" label={t('common.orgUnit') + ' (OU)'} placeholder={t('csrs.departmentPlaceholder')} />
            <Input name="description" label={t('common.description')} placeholder={t('cas.descriptionPlaceholder')} />
          </div>
        </div>

        <div className="space-y-4">
          <h3 className="text-sm font-semibold text-text-primary">{t('cas.create.keyStorage')}</h3>
          <div className="flex gap-2">
            <label className={cn(
              'flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg border text-sm cursor-pointer transition-all',
              createFormKeyStorage === 'local'
                ? 'border-accent-primary bg-accent-primary-op10 text-accent-primary font-semibold'
                : 'border-border hover:border-border-hover text-text-secondary'
            )}>
              <input
                type="radio"
                name="keyStorage"
                value="local"
                className="sr-only"
                checked={createFormKeyStorage === 'local'}
                onChange={() => setCreateFormKeyStorage('local')}
              />
              {t('cas.create.keyStorageLocal')}
            </label>
            <label className={cn(
              'flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg border text-sm cursor-pointer transition-all',
              createFormKeyStorage === 'hsm'
                ? 'border-accent-primary bg-accent-primary-op10 text-accent-primary font-semibold'
                : 'border-border hover:border-border-hover text-text-secondary'
            )}>
              <input
                type="radio"
                name="keyStorage"
                value="hsm"
                className="sr-only"
                checked={createFormKeyStorage === 'hsm'}
                onChange={() => setCreateFormKeyStorage('hsm')}
              />
              {t('cas.create.keyStorageHsm')}
            </label>
          </div>
        </div>

        {createFormKeyStorage === 'local' && (
        <div className="space-y-4">
          <h3 className="text-sm font-semibold text-text-primary">{t('cas.keyConfiguration')}</h3>
          <div className="grid grid-cols-2 gap-4">
            <Select
              label={t('common.keyAlgorithm')}
              options={[
                { value: 'RSA', label: 'RSA' },
                { value: 'ECDSA', label: 'ECDSA' }
              ]}
              value={createFormKeyAlgo}
              onChange={(value) => {
                setCreateFormKeyAlgo(value)
                setCreateFormKeySize(value === 'ECDSA' ? 'prime256v1' : '2048')
              }}
            />
            <Select
              label={t('common.keySize')}
              options={createFormKeyAlgo === 'ECDSA' ? [
                { value: 'prime256v1', label: 'P-256 (256 bits)' },
                { value: 'secp384r1', label: 'P-384 (384 bits)' },
                { value: 'secp521r1', label: 'P-521 (521 bits)' }
              ] : [
                { value: '2048', label: '2048 bits' },
                { value: '3072', label: '3072 bits' },
                { value: '4096', label: '4096 bits' }
              ]}
              value={createFormKeySize}
              onChange={(value) => setCreateFormKeySize(value)}
            />
          </div>
        </div>
        )}

        {createFormKeyStorage === 'hsm' && (
        <div className="space-y-4">
          <h3 className="text-sm font-semibold text-text-primary">{t('cas.keyConfiguration')}</h3>
          {!hsmLoading && hsmProviders.length === 0 ? (
            <div className="px-3 py-2 rounded-lg border border-status-warning bg-status-warning-op10 text-xs text-status-warning">
              {t('cas.create.hsmNoProviders')}
            </div>
          ) : (
            <>
              <Select
                label={t('cas.create.hsmProvider')}
                options={hsmProviders.map(p => ({
                  value: p.id.toString(),
                  label: `${p.name} (${p.provider_type})`
                }))}
                value={createFormHsmProviderId}
                onChange={(v) => { setCreateFormHsmProviderId(v); setCreateFormHsmKeyId('') }}
                required
              />
              <div>
                <label className="block text-xs font-medium text-text-secondary mb-1.5">
                  {t('cas.create.hsmKeyMode')}
                </label>
                <div className="flex gap-2">
                  <label className={cn(
                    'flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg border text-sm cursor-pointer transition-all',
                    createFormHsmKeyMode === 'generate'
                      ? 'border-accent-primary bg-accent-primary-op10 text-accent-primary font-semibold'
                      : 'border-border hover:border-border-hover text-text-secondary'
                  )}>
                    <input
                      type="radio"
                      name="hsmKeyMode"
                      value="generate"
                      className="sr-only"
                      checked={createFormHsmKeyMode === 'generate'}
                      onChange={() => setCreateFormHsmKeyMode('generate')}
                    />
                    {t('cas.create.hsmKeyModeGenerate')}
                  </label>
                  <label className={cn(
                    'flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg border text-sm cursor-pointer transition-all',
                    createFormHsmKeyMode === 'existing'
                      ? 'border-accent-primary bg-accent-primary-op10 text-accent-primary font-semibold'
                      : 'border-border hover:border-border-hover text-text-secondary'
                  )}>
                    <input
                      type="radio"
                      name="hsmKeyMode"
                      value="existing"
                      className="sr-only"
                      checked={createFormHsmKeyMode === 'existing'}
                      onChange={() => setCreateFormHsmKeyMode('existing')}
                    />
                    {t('cas.create.hsmKeyModeExisting')}
                  </label>
                </div>
              </div>

              {createFormHsmKeyMode === 'generate' && (
                <div className="grid grid-cols-2 gap-4">
                  <Input
                    label={t('cas.create.hsmKeyLabel')}
                    value={createFormHsmKeyLabel}
                    onChange={(e) => setCreateFormHsmKeyLabel(e.target.value)}
                    placeholder="ca-signing-key-1"
                    helperText={t('cas.create.hsmKeyLabelHelp')}
                    required
                  />
                  <Select
                    label={t('cas.create.hsmKeyAlgorithm')}
                    options={[
                      { value: 'RSA-2048', label: 'RSA-2048' },
                      { value: 'RSA-3072', label: 'RSA-3072' },
                      { value: 'RSA-4096', label: 'RSA-4096' },
                      { value: 'EC-P256', label: 'EC-P256' },
                      { value: 'EC-P384', label: 'EC-P384' },
                      { value: 'EC-P521', label: 'EC-P521' }
                    ]}
                    value={createFormHsmKeyAlgorithm}
                    onChange={(v) => setCreateFormHsmKeyAlgorithm(v)}
                  />
                </div>
              )}

              {createFormHsmKeyMode === 'existing' && (
                createFormHsmProviderId && hsmKeys.length === 0 ? (
                  <div className="px-3 py-2 rounded-lg border border-status-warning bg-status-warning-op10 text-xs text-status-warning">
                    {t('cas.create.hsmNoUnusedKeys')}
                  </div>
                ) : (
                  <Select
                    label={t('cas.create.hsmExistingKey')}
                    options={hsmKeys.map(k => ({
                      value: k.id.toString(),
                      label: `${k.label} (${k.algorithm})`
                    }))}
                    value={createFormHsmKeyId}
                    onChange={(v) => setCreateFormHsmKeyId(v)}
                    required
                  />
                )
              )}
            </>
          )}
        </div>
        )}

        <div className="space-y-4">
          <h3 className="text-sm font-semibold text-text-primary">{t('common.validityPeriod')}</h3>
          <Select
            label={t('common.validityPeriod')}
            options={[
              { value: '5', label: t('cas.yearsValidity', { count: 5 }) },
              { value: '10', label: t('cas.yearsValidity', { count: 10 }) },
              { value: '15', label: t('cas.yearsValidity', { count: 15 }) },
              { value: '20', label: t('cas.yearsValidity', { count: 20 }) }
            ]}
            value={createFormValidity}
            onChange={(value) => setCreateFormValidity(value)}
          />
        </div>

        <div className="space-y-4">
          <h3 className="text-sm font-semibold text-text-primary">{t('cas.caType')}</h3>
          <Select
            label={t('common.type')}
            options={[
              { value: 'root', label: t('cas.rootCASelfSigned') },
              { value: 'intermediate', label: t('cas.intermediateCASigned') }
            ]}
            value={createFormType}
            onChange={(value) => setCreateFormType(value)}
          />
          {createFormType === 'intermediate' && (
            <Select
              label={t('cas.parentCA')}
              options={cas.map(ca => ({
                value: ca.id.toString(),
                label: ca.name || ca.descr || ca.common_name
              }))}
              value={createFormParentCAId}
              onChange={(value) => setCreateFormParentCAId(value)}
              required
            />
          )}
        </div>

        {/* Advanced Constraints (RFC 5280) */}
        <div className="space-y-4">
          <button
            type="button"
            className="flex items-center gap-2 text-sm font-semibold text-text-secondary hover:text-text-primary transition-colors"
            onClick={() => setShowAdvanced(!showAdvanced)}
          >
            {showAdvanced ? <CaretDown size={14} /> : <CaretRight size={14} />}
            {t('cas.advancedConstraints')}
          </button>
          {showAdvanced && (
            <div className="space-y-4 pl-2 border-l-2 border-border">
              <Input
                label={t('cas.pathLength')}
                type="number"
                min="0"
                value={createFormPathLength}
                onChange={(e) => setCreateFormPathLength(e.target.value)}
                placeholder={t('cas.pathLengthPlaceholder')}
              />
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 pt-4 border-t border-border">
          <Button type="button" variant="secondary" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button
            type="submit"
            disabled={
              createFormKeyStorage === 'hsm' && (
                hsmProviders.length === 0 ||
                (createFormHsmKeyMode === 'existing' && !!createFormHsmProviderId && hsmKeys.length === 0)
              )
            }
          >
            {t('common.createCA')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
