import { useTranslation } from 'react-i18next'
import { HardDrives, Gear, Database, ShieldCheck, Download, Trash, WarningCircle } from '@phosphor-icons/react'
import { Button, DetailHeader, DetailSection, DetailGrid, DetailField, DetailContent } from '../../components'
import { formatDate } from '../../lib/utils'
import DatabaseBackendSection from './DatabaseBackendSection'

export default function DatabaseSection({ dbStats, handleOptimizeDb, handleIntegrityCheck, handleExportDb, handleResetDb }) {
  const { t } = useTranslation()
  return (
    <DetailContent>
      <DetailHeader
        icon={HardDrives}
        title={t('settings.helpDatabase')}
        subtitle={t('settings.databaseSubtitle')}
      />
      <DatabaseBackendSection />
      <DetailSection title={t('settings.databaseStatistics')} icon={HardDrives} iconClass="icon-bg-teal">
        <DetailGrid>
          <DetailField
            label={t('settings.totalCertificates')}
            value={dbStats?.certificates || '-'}
          />
          <DetailField
            label={t('common.cas')}
            value={dbStats?.cas || '-'}
          />
          <DetailField
            label={t('settings.databaseSize')}
            value={dbStats?.size || '-'}
          />
          <DetailField
            label={t('settings.lastOptimized')}
            value={dbStats?.last_optimized && dbStats.last_optimized !== 'Never' ? formatDate(dbStats.last_optimized) : '-'}
          />
        </DetailGrid>
      </DetailSection>

      <DetailSection title={t('settings.maintenance')} icon={Gear} iconClass="icon-bg-teal">
        <div className="space-y-3">
          <div className="flex flex-wrap gap-3">
            <Button type="button" size="sm" variant="secondary" onClick={handleOptimizeDb}>
              <Database size={16} />
              {t('settings.optimizeDatabase')}
            </Button>
            <Button type="button" size="sm" variant="secondary" onClick={handleIntegrityCheck}>
              <ShieldCheck size={16} />
              {t('settings.integrityCheck')}
            </Button>
            <Button type="button" size="sm" variant="secondary" onClick={handleExportDb}>
              <Download size={16} />
              {t('settings.exportDatabase')}
            </Button>
          </div>
        </div>
      </DetailSection>

      <DetailSection title={t('settings.dangerZone')} icon={WarningCircle} iconClass="icon-bg-orange" className="mt-4">
        <div className="p-4 status-danger-bg status-danger-border border rounded-lg">
          <h4 className="text-sm font-semibold text-status-danger mb-2">⚠️ {t('settings.databaseReset')}</h4>
          <p className="text-xs text-text-secondary mb-3">
            {t('settings.databaseResetDesc')}
          </p>
          <Button type="button" variant="danger" size="sm" onClick={handleResetDb}>
            <Trash size={16} />
            {t('settings.resetDatabase')}
          </Button>
        </div>
      </DetailSection>
    </DetailContent>
  )
}
