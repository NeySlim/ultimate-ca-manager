import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { AtelierDialog, Btn, Notice } from '../../components/atelier'

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

  if (!data) return null
  const close = () => { onClose(); window.location.reload() }

  return (
    <AtelierDialog title={t('settings.restoreReportTitle')} size="narrow" onClose={close}>
      <p>
        {restored
          ? t('settings.backupRestored', { users: data.users || 0, cas: data.cas || 0, certs: data.certificates || 0 })
          : t('settings.restoreReportNothingRestored')}
      </p>
      {todo.length > 0 && (
        <Notice tone="warn">
          <strong>{t('settings.restoreReportTodo')}</strong>
          <ul className="restore-todo">{todo.map((line, i) => <li key={i}>{line}</li>)}</ul>
        </Notice>
      )}
      {restored && (
        <p className="muted small">
          {data.restart_requested
            ? t('settings.restoreReportRestartRequested')
            : t('settings.restoreReportRestartManual', { detail: data.restart_detail || '' })}
        </p>
      )}
      <p className="muted small">
        {t('settings.restoreReportAudit')}{' '}
        <Link to="/audit" className="text-link" data-link="">{t('settings.restoreReportAuditLink')}</Link>
      </p>
      <div className="modal-actions">
        <Btn tone="primary" write={false} onClick={close}>{t('common.close')}</Btn>
      </div>
    </AtelierDialog>
  )
}
