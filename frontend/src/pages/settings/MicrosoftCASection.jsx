import { useTranslation } from 'react-i18next'
import ReactMarkdown from 'react-markdown'
import { WindowsLogo, Plus, TestTube, ArrowsClockwise, ClockClockwise, Broadcast, Database, Pulse, Power, PencilSimple, Trash } from '@phosphor-icons/react'
import { Button, Badge, HelpCard } from '../../components'
import { formatDate } from '../../lib/utils'

export default function MicrosoftCASection({ mscaConnections, mscaLoading, mscaTesting, handleMscaCreate, handleMscaEdit, handleMscaToggle, handleMscaTest, handleMscaSyncCrl, handleMscaPublishCrl, handleMscaInventorySync, handleMscaCaControl, setMscaConfirmDelete, hasPermission }) {
  const { t } = useTranslation()
  // Test, enable and edit write the connection (write:settings), deleting it is delete:settings
  const canWrite = hasPermission('write:settings')
  const canDelete = hasPermission('delete:settings')
  return (
    <>

      <HelpCard variant="info" title={t('msca.helpTitle')}>
        <div className="prose prose-sm dark:prose-invert max-w-none [&>p]:my-1 [&>ul]:my-1 [&>ul]:pl-4">
          <ReactMarkdown>{t('msca.helpDescription')}</ReactMarkdown>
        </div>
      </HelpCard>

      {mscaLoading ? (
        <div className="flex items-center justify-center py-12">
          <div className="w-6 h-6 border-2 border-accent-primary-op30 border-t-accent-primary rounded-full animate-spin" />
        </div>
      ) : mscaConnections.length === 0 ? (
        <div className="text-center py-12">
          <WindowsLogo size={48} className="mx-auto text-text-tertiary mb-3" />
          <p className="text-text-secondary mb-1">{t('msca.noConnections')}</p>
          <p className="text-xs text-text-tertiary mb-4">{t('msca.noConnectionsDesc')}</p>
          {hasPermission('admin:system') && (
            <Button type="button" onClick={handleMscaCreate} data-write>
              <Plus size={14} /> {t('msca.addConnection')}
            </Button>
          )}
        </div>
      ) : (
        <div className="sf-group">
          {hasPermission('admin:system') && (
            <div className="sf-group-head">
              <span />
              <div className="sf-group-actions">
                <Button type="button" variant="secondary" onClick={handleMscaCreate} data-write>
                  <Plus size={16} /> {t('msca.addConnection')}
                </Button>
              </div>
            </div>
          )}
          {/* The mockup's record list: name and state, server and last runs, then the actions */}
          <ul className="sf-records">
            {mscaConnections.map(conn => (
              <li key={conn.id}>
                <div className="sf-record-main">
                  <span className="sf-record-title">
                    <strong>{conn.name}</strong>
                    <Badge variant={conn.enabled ? 'success' : 'secondary'} size="sm">
                      {conn.enabled ? t('common.enabled') : t('common.disabled')}
                    </Badge>
                    <Badge variant="outline" size="sm">{conn.auth_method}</Badge>
                  </span>
                  <span className="sf-record-meta">
                    {conn.server} {conn.ca_name ? `· ${conn.ca_name}` : ''} · {t('msca.defaultTemplate')}{t('work.sep')}{conn.default_template}
                  </span>
                  {conn.last_test_at && (
                    <span className="sf-record-meta">
                      {t('msca.testConnection')}{t('work.sep')}{conn.last_test_result === 'success' ? '✓' : '✗'} {formatDate(conn.last_test_at)}
                    </span>
                  )}
                  {conn.crl_sync_enabled && conn.last_crl_sync_at && (
                    <span className="sf-record-meta">
                      {t('msca.lastCrlSync')}{t('work.sep')}{conn.last_crl_sync_result?.startsWith('success') ? '✓' : '✗'} {formatDate(conn.last_crl_sync_at)}
                    </span>
                  )}
                  {conn.winrm_enabled && (
                    <span className="sf-record-meta">
                      {t('msca.adminChannel')}{t('work.sep')}WinRM {conn.winrm_transport} · {conn.winrm_host || conn.server}:{conn.winrm_port}
                    </span>
                  )}
                  {conn.inventory_sync_enabled && conn.last_inventory_sync_at && (
                    <span className="sf-record-meta">
                      {t('msca.lastInventorySync')}{t('work.sep')}{conn.last_inventory_sync_result?.startsWith('success') ? '✓' : '✗'} {formatDate(conn.last_inventory_sync_at)}
                    </span>
                  )}
                </div>
                <div className="sf-record-actions">
                  {canWrite && (
                    <Button type="button" variant="secondary" onClick={() => handleMscaTest(conn)} disabled={mscaTesting}
                      aria-label={t('msca.testConnection')} title={t('msca.testConnection')}>
                      {mscaTesting ? <ArrowsClockwise size={16} className="animate-spin" /> : <TestTube size={16} />}
                    </Button>
                  )}
                  {conn.winrm_enabled && hasPermission('admin:system') && (
                    <Button type="button" variant="secondary" onClick={() => handleMscaCaControl(conn)} disabled={!conn.enabled}
                      aria-label={t('msca.caControl')} title={t('msca.caControl')}>
                      <Pulse size={16} />
                    </Button>
                  )}
                  {conn.crl_sync_enabled && hasPermission('write:certificates') && (
                    <Button type="button" variant="secondary" onClick={() => handleMscaSyncCrl(conn)} disabled={mscaTesting || !conn.enabled}
                      aria-label={t('msca.syncCrlNow')} title={t('msca.syncCrlNow')}>
                      <ClockClockwise size={16} />
                    </Button>
                  )}
                  {conn.winrm_enabled && hasPermission('admin:system') && (
                    <Button type="button" variant="secondary" onClick={() => handleMscaPublishCrl(conn)} disabled={mscaTesting || !conn.enabled}
                      aria-label={t('msca.publishCrl')} title={t('msca.publishCrl')}>
                      <Broadcast size={16} />
                    </Button>
                  )}
                  {conn.inventory_sync_enabled && hasPermission('admin:system') && (
                    <Button type="button" variant="secondary" onClick={() => handleMscaInventorySync(conn)} disabled={mscaTesting || !conn.enabled}
                      aria-label={t('msca.inventorySyncNow')} title={t('msca.inventorySyncNow')}>
                      <Database size={16} />
                    </Button>
                  )}
                  {canWrite && (
                    <>
                      <Button type="button" variant="secondary" onClick={() => handleMscaToggle(conn)}
                        aria-label={conn.enabled ? t('common.disable') : t('common.enable')} title={conn.enabled ? t('common.disable') : t('common.enable')}>
                        <Power size={16} />
                      </Button>
                      <Button type="button" variant="secondary" onClick={() => handleMscaEdit(conn)}
                        aria-label={t('common.edit')} title={t('common.edit')}>
                        <PencilSimple size={16} />
                      </Button>
                    </>
                  )}
                  {canDelete && (
                    <Button type="button" variant="danger" onClick={() => setMscaConfirmDelete(conn)}
                      aria-label={t('common.delete')} title={t('common.delete')}>
                      <Trash size={16} />
                    </Button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  )
}
