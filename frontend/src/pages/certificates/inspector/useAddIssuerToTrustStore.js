/** The offer of the chain panel and the « ⋯ » menu to trust the issuing CA of an incomplete chain. */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { usePermission } from '../../../hooks'
import { useNotification } from '../../../contexts'
import { certificatesService, truststoreService } from '../../../services'

/** Adds the issuing CA of an incomplete chain to the trust store; the chain is read again after. */
export function useAddIssuerToTrustStore(cert, onChanged) {
  const { t } = useTranslation()
  const { canWrite } = usePermission()
  const { showSuccess, showError } = useNotification()
  const [adding, setAdding] = useState(false)
  const offered = cert?.chain_status?.status === 'incomplete' && !!cert?.caref && canWrite('truststore')
  const add = async () => {
    setAdding(true)
    try {
      await truststoreService.addFromCA(cert.caref)
      showSuccess(t('details.addedToTrustStore'))
      const res = await certificatesService.getById(cert.id)
      if (res?.data) onChanged?.({ ...cert, ...res.data })
    } catch (err) {
      showError(err?.message || t('details.addToTrustStoreFailed'))
    } finally {
      setAdding(false)
    }
  }
  return { offered, adding, add }
}
