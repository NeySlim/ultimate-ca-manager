import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Modal, Button } from '../../components'

// What a restore did and what it left to do. With nothing to do it is the old short
// success and a reload; with warnings, or a restart to make by hand, it stays until closed.
export default function RestoreReport({ data, onClose }) {
  const { t } = useTranslation()
  const todo = Array.isArray(data?.todo) ? data.todo : []
  // An archive with no section changed nothing: no restart was asked.
  const restored = !!data && (data.restart_requested !== undefined || (data.sections_carried || []).length > 0)

  // A restart not obtained is an instruction the operator must read: no reload under it
  const restartByHand = data?.restart_requested === false

  useEffect(() => {
    if (!data || todo.length || restartByHand) return undefined
    const timer = setTimeout(() => window.location.reload(), 2000)
    return () => clearTimeout(timer)
  }, [data, todo.length, restartByHand])

  const close = () => { onClose(); window.location.reload() }

  return (
    <Modal open={!!data} onClose={close} title={t('settings.restoreReportTitle')}>
      {data && (
        <div className="space-y-4">
          <p className="text-sm text-text-primary">
            {restored
              ? t('settings.backupRestored', {
                users: data.users || 0, cas: data.cas || 0, certs: data.certificates || 0,
              })
              : t('settings.restoreReportNothingRestored')}
          </p>
          {todo.length > 0 && (
            <div className="p-3 status-warning-bg status-warning-border border rounded-lg">
              <p className="text-sm status-warning-text font-medium">{t('settings.restoreReportTodo')}</p>
              <ul className="mt-1 list-disc pl-5 text-xs status-warning-text">
                {todo.map((line, i) => <li key={i}>{line}</li>)}
              </ul>
            </div>
          )}
          {restored && (
            <p className="text-xs text-text-secondary">
              {data.restart_requested
                ? t('settings.restoreReportRestartRequested')
                : t('settings.restoreReportRestartManual', { detail: data.restart_detail || '' })}
            </p>
          )}
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
