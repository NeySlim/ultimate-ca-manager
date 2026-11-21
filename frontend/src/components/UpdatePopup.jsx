/**
 * UpdatePopup — optional "what's new" window shown once per user after an
 * update was installed (#308).
 *
 * Server side: the admin enables it in Settings › Updates (off by default,
 * `popup_enabled` in the update settings). Per user: the last acknowledged
 * version lives in the server-side preferences (`update_popup_seen_version`),
 * so dismissing it on one browser dismisses it everywhere.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import ReactMarkdown from 'react-markdown'
import { AtelierDialog } from './atelier/AtelierDialog'
import { apiClient } from '../services'
import { useAuth } from '../contexts/AuthContext'
import { getPreferences, persistPreference } from '../stores/userPreferencesStore'
import { formatDate } from '../lib/utils'
import { MARKDOWN_COMPONENTS } from './atelier/markdown'

export function UpdatePopup() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const [info, setInfo] = useState(null)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (!user) {
      setOpen(false)
      setInfo(null)
      return
    }
    let cancelled = false
    apiClient.get('/system/updates/whatsnew')
      .then((response) => {
        if (cancelled) return
        const data = response?.data || response || {}
        if (!data.enabled || !data.version) return
        if (data.baseline_version === data.version) return
        if (getPreferences().update_popup_seen_version === data.version) return
        setInfo(data)
        setOpen(true)
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [user?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const dismiss = () => {
    setOpen(false)
    if (info?.version) persistPreference('update_popup_seen_version', info.version)
  }

  if (!info || !open) return null

  return (
    <AtelierDialog title={t('updatePopup.title', { version: info.version })} size="wide" onClose={dismiss} testId="update-popup"
      subtitle={info.installed_at ? t('updatePopup.installedOn', { date: formatDate(info.installed_at) }) : undefined}>
      {info.release_notes ? (
        <div className="event-detail" style={{ maxHeight: '50dvh', overflow: 'auto' }}>
          <ReactMarkdown components={MARKDOWN_COMPONENTS}>{info.release_notes}</ReactMarkdown>
        </div>
      ) : (
        <p className="event-detail">{t('updatePopup.noNotes')}</p>
      )}
      <div className="modal-actions">
        <button type="button" className="btn primary" data-action="close-modal" data-write="false" onClick={dismiss}>{t('common.close')}</button>
      </div>
    </AtelierDialog>
  )
}
