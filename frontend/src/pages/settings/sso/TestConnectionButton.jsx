import { useTranslation } from 'react-i18next'
import { Button, LoadingSpinner } from '../../../components'

/** The connection test runs on the SAVED provider: it waits for unsaved edits to be saved. */
export default function TestConnectionButton({ onClick, testing, dirty, icon: Icon }) {
  const { t } = useTranslation()
  return (
    <div className="space-y-1">
      <Button type="button" variant="secondary" size="sm" onClick={onClick} disabled={testing || dirty} className="gap-1.5">
        {testing ? <LoadingSpinner size="xs" /> : <Icon size={14} />}
        {t('sso.testConnection')}
      </Button>
      {dirty && <p className="text-xs text-text-tertiary">{t('sso.saveBeforeTest')}</p>}
    </div>
  )
}
