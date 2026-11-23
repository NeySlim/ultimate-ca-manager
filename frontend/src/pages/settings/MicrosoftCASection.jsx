import { useTranslation } from 'react-i18next'
import ReactMarkdown from 'react-markdown'
import { Btn, IconBtn, Pill, RecordList, RecordRow, SkeletonPanel, EmptyBlock } from '../../components/atelier'
import { Notice } from '../../components/atelier/Form'
import { SettingsGroup } from '../../components/atelier/SettingsView'
import { formatDate } from '../../lib/utils'

// The help's paragraphs run inline in the notice; its list keeps its items
const NOTICE_MARKDOWN = { p: ({ children }) => <>{children} </> }
// A connection's authentication method in the words of its form
const AUTH_WORDS = { certificate: 'msca.authCertificate', kerberos: 'msca.authKerberos', basic: 'msca.authBasic' }

export default function MicrosoftCASection({ mscaConnections, mscaLoading, mscaTesting, handleMscaCreate, handleMscaEdit, handleMscaToggle, handleMscaTest, handleMscaSyncCrl, handleMscaPublishCrl, handleMscaInventorySync, handleMscaCaControl, setMscaConfirmDelete, hasPermission }) {
  const { t } = useTranslation()
  // The outcome of a test or a sync in words, not a check mark
  const outcome = (ok) => t(ok ? 'common.success' : 'common.failed')
  // Test, enable and edit write the connection (write:settings), deleting it is delete:settings
  const canWrite = hasPermission('write:settings')
  const canDelete = hasPermission('delete:settings')
  const admin = hasPermission('admin:system')
  const sep = t('work.sep')

  const help = (
    <Notice><strong>{t('msca.helpTitle')}</strong>{' '}<ReactMarkdown components={NOTICE_MARKDOWN}>{t('msca.helpDescription')}</ReactMarkdown></Notice>
  )
  if (mscaLoading) return <>{help}<SkeletonPanel label={t('common.loading')} /></>
  if (mscaConnections.length === 0) {
    return (
      <>
        {help}
        <EmptyBlock id="msca" icon="plug" title={t('msca.noConnections')} text={t('msca.noConnectionsDesc')}
          action={admin ? { label: t('msca.addConnection'), icon: 'plus', onClick: handleMscaCreate, primary: true } : undefined} />
      </>
    )
  }
  // The mockup's record list: name and state, server and last runs, then the actions
  return (
    <>
      {help}
      <SettingsGroup legend={t('settings.tabs.microsoftCA')} legendHidden grid={false}>
        <RecordList columns>
          {mscaConnections.map(conn => (
            <RecordRow key={conn.id} title={conn.name}
              meta={<>{conn.server}{conn.ca_name ? ` · ${conn.ca_name}` : ''} · {t('msca.defaultTemplate')}{sep}{conn.default_template}</>}
              extra={<>
                {conn.last_test_at && (
                  <span className="rl-meta">{t('msca.testConnection')}{sep}{outcome(conn.last_test_result === 'success')}, {formatDate(conn.last_test_at)}</span>
                )}
                {conn.crl_sync_enabled && conn.last_crl_sync_at && (
                  <span className="rl-meta">{t('msca.lastCrlSync')}{sep}{outcome(conn.last_crl_sync_result?.startsWith('success'))}, {formatDate(conn.last_crl_sync_at)}</span>
                )}
                {conn.winrm_enabled && (
                  <span className="rl-meta">{t('msca.adminChannel')}{sep}WinRM {conn.winrm_transport} · {conn.winrm_host || conn.server}:{conn.winrm_port}</span>
                )}
                {conn.inventory_sync_enabled && conn.last_inventory_sync_at && (
                  <span className="rl-meta">{t('msca.lastInventorySync')}{sep}{outcome(conn.last_inventory_sync_result?.startsWith('success'))}, {formatDate(conn.last_inventory_sync_at)}</span>
                )}
              </>}
              badge={(
                <span className="row-actions">
                  <Pill tone={conn.enabled ? 'good' : 'muted'} label={conn.enabled ? t('common.enabled') : t('common.disabled')} />
                  <Pill icon="key" label={AUTH_WORDS[conn.auth_method] ? t(AUTH_WORDS[conn.auth_method]) : conn.auth_method} />
                </span>
              )}
              action={<>
                {canWrite && <IconBtn icon="send" label={t('msca.testConnection')} disabled={mscaTesting || undefined} onClick={() => handleMscaTest(conn)} />}
                {conn.winrm_enabled && admin && (
                  <IconBtn icon="activity" label={t('msca.caControl')} disabled={!conn.enabled || undefined} onClick={() => handleMscaCaControl(conn)} />
                )}
                {conn.crl_sync_enabled && hasPermission('write:certificates') && (
                  <IconBtn icon="refresh" write label={t('msca.syncCrlNow')} disabled={mscaTesting || !conn.enabled || undefined} onClick={() => handleMscaSyncCrl(conn)} />
                )}
                {conn.winrm_enabled && admin && (
                  <IconBtn icon="crl" write label={t('msca.publishCrl')} disabled={mscaTesting || !conn.enabled || undefined} onClick={() => handleMscaPublishCrl(conn)} />
                )}
                {conn.inventory_sync_enabled && admin && (
                  <IconBtn icon="download" write label={t('msca.inventorySyncNow')} disabled={mscaTesting || !conn.enabled || undefined} onClick={() => handleMscaInventorySync(conn)} />
                )}
                {canWrite && (
                  <>
                    <IconBtn icon={conn.enabled ? 'block' : 'check'} write label={conn.enabled ? t('common.disable') : t('common.enable')} onClick={() => handleMscaToggle(conn)} />
                    <IconBtn icon="settings" label={t('common.edit')} onClick={() => handleMscaEdit(conn)} />
                  </>
                )}
                {canDelete && <IconBtn icon="close" write label={t('common.delete')} onClick={() => setMscaConfirmDelete(conn)} />}
              </>} />
          ))}
        </RecordList>
        {admin && (
          <div className="settings-actions">
            <Btn tone="primary" icon="plus" onClick={handleMscaCreate}>{t('msca.addConnection')}</Btn>
          </div>
        )}
      </SettingsGroup>
    </>
  )
}
