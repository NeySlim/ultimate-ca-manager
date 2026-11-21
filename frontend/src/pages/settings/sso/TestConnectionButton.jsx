import { useTranslation } from 'react-i18next'
import { Btn, Icon } from '../../../components/atelier'

/**
 * The connection test of a provider (`.settings-test` of the mockup): it runs on the SAVED
 * provider, so it waits for unsaved edits to be saved; its outcome follows the button.
 */
export default function TestConnectionButton({ onClick, testing, dirty, status }) {
  const { t } = useTranslation()
  return (
    <div className="settings-test">
      <Btn icon="send" onClick={onClick} disabled={testing || dirty || undefined}>
        {testing ? t('common.testing') : t('sso.testConnection')}
      </Btn>
      {status === 'success' && <p className="test-result good" role="status"><Icon name="check" /><span>{t('sso.testConnectionSuccess')}</span></p>}
      {status === 'error' && <p className="test-result bad" role="status"><Icon name="warning" /><span>{t('sso.testConnectionFailed')}</span></p>}
      {dirty && <p className="test-result muted"><Icon name="help" /><span>{t('sso.saveBeforeTest')}</span></p>}
    </div>
  )
}
