import { useTranslation } from 'react-i18next'
import { Btn, Facts, RecordList, RecordRow } from '../../components/atelier'
import { SettingsGroup } from '../../components/atelier/SettingsView'
import { formatBytes } from '../../lib/fileSize'
import { formatDate } from '../../lib/utils'
import DatabaseBackendSection from './DatabaseBackendSection'
import { fact } from '../../components/atelier/facts'

export default function DatabaseSection({ dbStats, handleOptimizeDb, handleIntegrityCheck, handleExportDb, handleResetDb }) {
  const { t, i18n } = useTranslation()
  return (
    <>
      <DatabaseBackendSection />
      <SettingsGroup legend={t('settings.databaseStatistics')} grid={false}>
        <Facts items={[
          fact(t('settings.totalCertificates'), dbStats?.certificates),
          fact(t('common.cas'), dbStats?.cas),
          fact(t('settings.databaseSize'), dbStats?.size_mb ? formatBytes(dbStats.size_mb * 1024 * 1024, i18n?.language) : null),
          fact(t('settings.lastOptimized'), dbStats?.last_optimized && dbStats.last_optimized !== 'Never' ? formatDate(dbStats.last_optimized) : null),
        ]} />
      </SettingsGroup>

      <SettingsGroup legend={t('settings.maintenance')} grid={false}>
        <div className="settings-actions">
          <Btn icon="server" onClick={handleOptimizeDb}>{t('settings.optimizeDatabase')}</Btn>
          <Btn icon="shield" onClick={handleIntegrityCheck}>{t('settings.integrityCheck')}</Btn>
          <Btn icon="download" onClick={handleExportDb}>{t('settings.exportDatabase')}</Btn>
        </div>
      </SettingsGroup>

      {/* The reset as a record of the mockup's list: what it does, its danger button on the right */}
      <SettingsGroup legend={t('settings.dangerZone')} grid={false}>
        <RecordList>
          <RecordRow title={t('settings.databaseReset')} meta={t('settings.databaseResetDesc')}
            action={<Btn tone="danger" icon="close" onClick={handleResetDb}>{t('settings.resetDatabase')}</Btn>} />
        </RecordList>
      </SettingsGroup>
    </>
  )
}
