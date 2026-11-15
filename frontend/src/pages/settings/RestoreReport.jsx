import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Modal, Button } from '../../components'

// What a restore did and what it left to do. With nothing to do it is the old short
// success and a reload; with warnings it stays until closed, then reloads.
export default function RestoreReport({ data, onClose }) {
  const { t } = useTranslation()
  const todo = Array.isArray(data?.todo) ? data.todo : []

  useEffect(() => {
    if (!data || todo.length) return undefined
    const timer = setTimeout(() => window.location.reload(), 2000)
    return () => clearTimeout(timer)
  }, [data, todo.length])

  const close = () => { onClose(); window.location.reload() }

  return (
    <Modal open={!!data} onClose={close} title={t('settings.restoreReportTitle')}>
      {data && (
        <div className="space-y-4">
          <p className="text-sm text-text-primary">
            {t('settings.backupRestored', {
              users: data.users || 0, cas: data.cas || 0, certs: data.certificates || 0,
            })}
          </p>
          {todo.length > 0 && (
            <div className="p-3 status-warning-bg status-warning-border border rounded-lg">
              <p className="text-sm status-warning-text font-medium">{t('settings.restoreReportTodo')}</p>
              <ul className="mt-1 list-disc pl-5 text-xs status-warning-text">
                {todo.map((line, i) => <li key={i}>{line}</li>)}
              </ul>
            </div>
          )}
          <p className="text-xs text-text-secondary">
            {data.restart_requested
              ? t('settings.restoreReportRestartRequested')
              : t('settings.restoreReportRestartManual', { detail: data.restart_detail || '' })}
          </p>
          <p className="text-xs text-text-secondary">
            {t('settings.restoreReportAudit')}{' '}
            <Link to="/audit" className="underline">{t('settings.restoreReportAuditLink')}</Link>
          </p>
          <div className="flex justify-end pt-2">
            <Button type="button" onClick={close}>{t('common.close')}</Button>
          </div>
        </div>
      )}
    </Modal>
  )
}
