import { useEffect, useState } from 'react'
import { casService, hsmService } from '../../services'
import { useNotification } from '../../contexts'
import { extractData } from '../../lib/utils'
import { AtelierDialog, Icon } from '../atelier'

/** Attach to a CA that holds only its certificate the key an HSM provider still holds (#458). */
export function AttachHsmKeyModal({ open, onClose, ca, onSuccess, t }) {
  const { showSuccess, showError } = useNotification()
  const [providers, setProviders] = useState(null)
  const [providerId, setProviderId] = useState('')
  const [keys, setKeys] = useState(null)
  const [listError, setListError] = useState('')
  const [chosen, setChosen] = useState('')
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!open) return
    let cancelled = false
    hsmService.getProviders()
      .then((res) => { if (!cancelled) setProviders(extractData(res) || []) })
      .catch((error) => { if (!cancelled) { setProviders([]); setListError(error?.message || t('common.operationFailed')) } })
    return () => { cancelled = true }
  }, [open, t])

  // The token is read again for each provider: what it holds now is what can be attached
  useEffect(() => {
    if (!open || !providerId) return
    let cancelled = false
    setKeys(null)
    setChosen('')
    setListError('')
    casService.listMatchingHsmKeys(ca.id, providerId)
      .then((res) => { if (!cancelled) setKeys(extractData(res)?.keys || []) })
      .catch((error) => { if (!cancelled) { setKeys([]); setListError(error?.message || t('common.operationFailed')) } })
    return () => { cancelled = true }
  }, [open, providerId, ca?.id, t])

  const reset = () => {
    setProviders(null)
    setProviderId('')
    setKeys(null)
    setListError('')
    setChosen('')
    setConfirming(false)
  }
  const handleClose = () => {
    if (busy) return
    reset()
    onClose()
  }

  const selected = (keys || []).find((k) => k.key_identifier === chosen)

  const handleAttach = async () => {
    if (!selected) return
    setBusy(true)
    try {
      const response = await casService.attachHsmKey(ca.id, Number(providerId), selected.key_identifier)
      showSuccess(t('cas.attachHsmKey.attached'))
      onSuccess?.(response?.data || response)
      reset()
      onClose()
    } catch (error) {
      showError(error?.message || t('common.operationFailed'))
      setConfirming(false)
    } finally {
      setBusy(false)
    }
  }

  if (!open) return null
  return (
    <AtelierDialog title={t('cas.useHsmKey')} size="narrow" onClose={handleClose} testId="attach-hsm-key-dialog">
      <p className="small muted" style={{ marginBottom: 12 }}>{ca?.common_name || ca?.descr}</p>
      {!confirming && (
        <>
          <p className="notice"><Icon name="key" /><span>{t('cas.attachHsmKey.intro')}</span></p>
          <div className="form-fields">
            {providers && providers.length === 0 && !listError && (
              <p className="notice warn" role="note"><Icon name="warning" /><span>{t('cas.attachHsmKey.noProviders')}</span></p>
            )}
            {providers && providers.length > 0 && (
              <div className="field full">
                <label htmlFor="attach-hsm-provider">{t('cas.attachHsmKey.provider')}</label>
                <select id="attach-hsm-provider" value={providerId} data-autofocus="" onChange={(e) => setProviderId(e.target.value)}>
                  <option value="" disabled hidden>{t('cas.create.choose')}</option>
                  {providers.map((p) => <option key={p.id} value={String(p.id)}>{`${p.name} (${p.provider_type})`}</option>)}
                </select>
              </div>
            )}
            {listError && <p className="field-error" role="alert"><Icon name="warning" /><span>{listError}</span></p>}
            {providerId && keys === null && !listError && <p className="small muted">{t('cas.attachHsmKey.reading')}</p>}
            {providerId && keys && keys.length === 0 && !listError && (
              <p className="notice warn" role="note"><Icon name="warning" /><span>{t('cas.attachHsmKey.noMatch')}</span></p>
            )}
            {keys && keys.length > 0 && (
              <fieldset className="field full">
                <legend>{t('cas.attachHsmKey.keys')}</legend>
                <div className="choice-grid">
                  {keys.map((k) => {
                    const blocked = k.held_by || k.refusal
                    return (
                      <label key={k.key_identifier} className="format-option">
                        <input type="radio" name="attachHsmKey" value={k.key_identifier} checked={chosen === k.key_identifier}
                          disabled={!!blocked} onChange={() => setChosen(k.key_identifier)} />
                        <span>{k.label || k.key_identifier}
                          <small className="mono">{`${t('cas.attachHsmKey.keyId')}: ${k.key_identifier} · ${k.algorithm}`}</small>
                          {k.held_by && <small>{t('cas.attachHsmKey.heldBy', { holder: k.held_by })}</small>}
                          {!k.held_by && k.refusal && <small>{k.refusal}</small>}
                        </span>
                      </label>
                    )
                  })}
                </div>
              </fieldset>
            )}
          </div>
          <div className="modal-actions">
            <button type="button" className="btn" onClick={handleClose}>{t('common.cancel')}</button>
            <button type="button" className="btn primary" data-write="" disabled={!selected} onClick={() => setConfirming(true)}>
              {t('common.continue')}
            </button>
          </div>
        </>
      )}
      {confirming && selected && (
        <>
          <p className="notice warn"><Icon name="key" /><span>{t('cas.attachHsmKey.confirmText', {
            label: selected.label || selected.key_identifier, id: selected.key_identifier, algorithm: selected.algorithm,
          })}</span></p>
          <div className="modal-actions">
            <button type="button" className="btn" disabled={busy} onClick={() => setConfirming(false)}>{t('common.back')}</button>
            <button type="button" className="btn primary" data-write="" disabled={busy} onClick={handleAttach}>
              <Icon name="key" />{t('cas.attachHsmKey.confirm')}
            </button>
          </div>
        </>
      )}
    </AtelierDialog>
  )
}
