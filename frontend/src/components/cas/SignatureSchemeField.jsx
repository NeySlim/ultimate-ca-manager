/**
 * RSA signature scheme of a CA (PKCS#1 v1.5 or RSA-PSS), with the switch.
 * Renders nothing for a CA whose key is not RSA.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { CompactField } from '../DetailCard'
import { Button } from '../Button'
import { casService } from '../../services'
import { useNotification } from '../../contexts/NotificationContext'
import { PSS_HSM_TYPES } from '../../lib/signatureName'
import { caKeyParts } from '../../lib/keyAlgorithms'

export function SignatureSchemeField({ ca, canWrite = false, onChanged }) {
  const { t } = useTranslation()
  if (caKeyParts(ca.key_type).family !== 'RSA') return null
  const isPss = ca.signature_scheme === 'pss'
  // Back to v1.5 is always possible; PSS needs a key that can sign it
  const pssPossible = ca.has_private_key && (!ca.uses_hsm || PSS_HSM_TYPES.includes(ca.hsm_provider_type))

  return (
    <CompactField autoIcon="signatureAlgorithm" label={t('cas.signatureScheme')}>
      <span>{t(isPss ? 'cas.signatureSchemePss' : 'cas.signatureSchemePkcs1v15')}</span>
      {canWrite && !ca.revoked && (isPss || pssPossible) && <SchemeSwitch ca={ca} isPss={isPss} onChanged={onChanged} />}
    </CompactField>
  )
}

function SchemeSwitch({ ca, isPss, onChanged }) {
  const { t } = useTranslation()
  const { showSuccess, showError, showConfirm } = useNotification()
  const [switching, setSwitching] = useState(false)
  const action = t(isPss ? 'cas.signatureSchemeUseV15' : 'cas.signatureSchemeUsePss')
  const handleSwitch = async () => {
    const confirmed = await showConfirm(
      t(isPss ? 'cas.signatureSchemeToV15Confirm' : 'cas.signatureSchemeToPssConfirm'),
      { title: t('cas.signatureScheme'), confirmText: action },
    )
    if (!confirmed) return
    setSwitching(true)
    try {
      const res = await casService.update(ca.id, { signatureScheme: isPss ? 'pkcs1v15' : 'pss' })
      const updated = res?.data || res
      showSuccess(t('cas.signatureSchemeChanged'))
      if (updated?.id) onChanged?.(updated)
      window.dispatchEvent(new CustomEvent('ucm:data-changed', { detail: { type: 'ca' } }))
    } catch (err) {
      showError(err?.message || t('cas.signatureSchemeChangeFailed'))
    } finally {
      setSwitching(false)
    }
  }

  return (
    <Button type="button" size="xs" variant="secondary" className="ml-2"
      onClick={handleSwitch} disabled={switching}>
      {action}
    </Button>
  )
}
