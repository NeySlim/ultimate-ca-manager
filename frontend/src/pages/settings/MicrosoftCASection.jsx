import { useTranslation } from 'react-i18next'
import ReactMarkdown from 'react-markdown'
import { WindowsLogo, Plus, TestTube, ArrowsClockwise, Power, PencilSimple, Trash } from '@phosphor-icons/react'
import { Button, Badge, HelpCard, DetailHeader, DetailContent, ExperimentalBadge } from '../../components'
import { formatDate } from '../../lib/utils'

export default function MicrosoftCASection({ mscaConnections, mscaLoading, mscaTesting, handleMscaCreate, handleMscaEdit, handleMscaToggle, handleMscaTest, setMscaConfirmDelete, hasPermission }) {
  const { t } = useTranslation()
  return (
    <DetailContent>
      <DetailHeader
        icon={WindowsLogo}
        title={t('msca.title')}
        subtitle={t('msca.subtitle')}
        badge={<ExperimentalBadge />}
      />

      <HelpCard variant="info" title={t('msca.helpTitle')} className="mb-4">
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
            <Button type="button" onClick={handleMscaCreate}>
              <Plus size={14} /> {t('msca.addConnection')}
            </Button>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {hasPermission('admin:system') && (
            <div className="flex justify-end mb-2">
              <Button type="button" size="sm" onClick={handleMscaCreate}>
                <Plus size={14} /> {t('msca.addConnection')}
              </Button>
            </div>
          )}
          {mscaConnections.map(conn => (
            <div key={conn.id} className="flex items-center justify-between p-4 bg-tertiary-50 border border-border rounded-lg">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg flex items-center justify-center icon-bg-indigo">
                  <WindowsLogo size={20} weight="bold" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-text-primary">{conn.name}</span>
                    <Badge variant={conn.enabled ? 'success' : 'secondary'} size="sm">
                      {conn.enabled ? t('common.enabled') : t('common.disabled')}
                    </Badge>
                    <Badge variant="outline" size="sm">{conn.auth_method}</Badge>
                  </div>
                  <p className="text-xs text-text-secondary">
                    {conn.server} {conn.ca_name ? `· ${conn.ca_name}` : ''} · {t('msca.defaultTemplate')}: {conn.default_template}
                  </p>
                  {conn.last_test_at && (
                    <p className="text-xs text-text-tertiary">
                      {t('msca.testConnection')}: {conn.last_test_result === 'success' ? '✓' : '✗'} {formatDate(conn.last_test_at)}
                    </p>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Button type="button" size="sm" variant="secondary" onClick={() => handleMscaTest(conn)} disabled={mscaTesting} title={t('msca.testConnection')}>
                  {mscaTesting ? <ArrowsClockwise size={14} className="animate-spin" /> : <TestTube size={14} />}
                </Button>
                <Button type="button" size="sm" variant="secondary" onClick={() => handleMscaToggle(conn)} title={conn.enabled ? t('common.disable') : t('common.enable')}>
                  <Power size={14} />
                </Button>
                <Button type="button" size="sm" variant="secondary" onClick={() => handleMscaEdit(conn)} title={t('common.edit')}>
                  <PencilSimple size={14} />
                </Button>
                <Button type="button" size="sm" variant="danger" onClick={() => setMscaConfirmDelete(conn)} title={t('common.delete')}>
                  <Trash size={14} />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </DetailContent>
  )
}
