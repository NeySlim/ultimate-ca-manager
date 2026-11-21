/**
 * Encryption at rest in the mockup's dialog (modal(), `.notice.warn`, `.checkbox-line`, `.field`).
 * Turning it on waits for three acknowledgements and the typed word; the master key, shown once
 * after, keeps its dialog open (Escape, Fermer) until it is downloaded and its storage confirmed.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Btn } from '../../components/atelier/Btn'
import { Input, Modal, ModalActions, Notice } from '../../components/atelier/Form'

const CONFIRM_WORD = 'ENCRYPT'
const ACKNOWLEDGEMENTS = [
  ['keyFile', 'settings.encryptionCheckKeyFile'],
  ['backup', 'settings.encryptionCheckBackup'],
  ['lostKeys', 'settings.encryptionCheckLostKeys'],
]

// Mounted only while open: what was ticked or typed starts over at each opening
export function EnableEncryptionDialog({ open, ...props }) {
  return open ? <EnableBody {...props} /> : null
}

function EnableBody({ loading = false, onConfirm, onClose }) {
  const { t } = useTranslation()
  const [checks, setChecks] = useState({})
  const [word, setWord] = useState('')
  const ready = ACKNOWLEDGEMENTS.every(([k]) => checks[k]) && word === CONFIRM_WORD
  const close = () => { if (!loading) onClose?.() }
  return (
    <Modal open title={t('settings.enableEncryption')} onClose={close}>
      <Notice tone="warn"><strong>{t('settings.encryptionWarningTitle')}</strong> {t('settings.encryptionWarningDesc')}</Notice>
      <div className="columns-list">
        {ACKNOWLEDGEMENTS.map(([k, label]) => (
          <label key={k} className="checkbox-line">
            <input type="checkbox" checked={!!checks[k]} onChange={(e) => setChecks((prev) => ({ ...prev, [k]: e.target.checked }))} />
            {t(label)}
          </label>
        ))}
      </div>
      <div className="form-fields" style={{ marginTop: 18 }}>
        <Input full label={t('settings.typeToConfirm', { word: CONFIRM_WORD })} value={word} placeholder={CONFIRM_WORD}
          onChange={(e) => setWord(e.target.value)} />
      </div>
      <ModalActions>
        <button type="button" className="btn" data-action="close-modal" disabled={loading || undefined} onClick={close}>{t('common.cancel')}</button>
        <Btn tone="primary" icon="lock" disabled={!ready || loading || undefined} onClick={onConfirm}>{t('settings.enableEncryption')}</Btn>
      </ModalActions>
    </Modal>
  )
}

export function MasterKeyBackupDialog({ open, ...props }) {
  return open ? <MasterKeyBody {...props} /> : null
}

function MasterKeyBody({ downloaded = false, onDownload, onDone }) {
  const { t } = useTranslation()
  const [confirmed, setConfirmed] = useState(false)
  const close = () => { if (confirmed) onDone?.() }
  return (
    <Modal open title={t('settings.masterKeyBackupTitle')} size="sm" onClose={close}>
      <Notice tone="bad" role="note"><strong>{t('settings.masterKeyBackupCritical')}</strong> {t('settings.masterKeyBackupDesc')}</Notice>
      <div className="event-detail">
        <p>{t('settings.masterKeyBackupInstructions')}</p>
        <ul>
          <li>{t('settings.masterKeyBackupTip1')}</li>
          <li>{t('settings.masterKeyBackupTip2')}</li>
          <li>{t('settings.masterKeyBackupTip3')}</li>
        </ul>
      </div>
      <p style={{ margin: '18px 0' }}>
        <Btn tone={downloaded ? undefined : 'primary'} write={false} icon="download" onClick={onDownload}>
          {downloaded ? t('settings.masterKeyDownloadAgain') : t('settings.masterKeyDownloadNow')}
        </Btn>
      </p>
      <label className="checkbox-line">
        <input type="checkbox" checked={confirmed} disabled={!downloaded} onChange={(e) => setConfirmed(e.target.checked)} />
        {t('settings.masterKeyBackupConfirm')}
      </label>
      <ModalActions>
        <Btn tone="primary" write={false} icon="check" disabled={!confirmed || undefined} onClick={onDone}>{t('common.done')}</Btn>
      </ModalActions>
    </Modal>
  )
}
