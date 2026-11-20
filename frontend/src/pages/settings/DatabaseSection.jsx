import { useTranslation } from 'react-i18next'
import {  Database, ShieldCheck, Download, Trash } from '@phosphor-icons/react'
import { Button } from '../../components'
import { formatBytes } from '../../lib/fileSize'
import { formatDate } from '../../lib/utils'
import DatabaseBackendSection from './DatabaseBackendSection'
import { FormGroup, FormProps } from '../../components/sectioned'

export default function DatabaseSection({ dbStats, handleOptimizeDb, handleIntegrityCheck, handleExportDb, handleResetDb }) {
  const { t, i18n } = useTranslation()
  return (
    <>
      <DatabaseBackendSection />
      <FormGroup title={t('settings.databaseStatistics')}>
        <FormProps items={[
          [t('settings.totalCertificates'), dbStats?.certificates ?? '—'],
          [t('common.cas'), dbStats?.cas ?? '—'],
          [t('settings.databaseSize'), dbStats?.size_mb ? formatBytes(dbStats.size_mb * 1024 * 1024, i18n?.language) : '—'],
          [t('settings.lastOptimized'), dbStats?.last_optimized && dbStats.last_optimized !== 'Never' ? formatDate(dbStats.last_optimized) : '—'],
        ]} />
      </FormGroup>

      <FormGroup title={t('settings.maintenance')}>
        <div className="sf-actions-row">
          <Button type="button" variant="secondary" onClick={handleOptimizeDb}>
            <Database size={16} />
            {t('settings.optimizeDatabase')}
          </Button>
          <Button type="button" variant="secondary" onClick={handleIntegrityCheck}>
            <ShieldCheck size={16} />
            {t('settings.integrityCheck')}
          </Button>
          <Button type="button" variant="secondary" onClick={handleExportDb}>
            <Download size={16} />
            {t('settings.exportDatabase')}
          </Button>
        </div>
      </FormGroup>

      {/* The reset as a record of the mockup's list: what it does, its danger button on the right */}
      <FormGroup title={t('settings.dangerZone')}>
        <ul className="sf-records">
          <li>
            <div className="sf-record-main">
              <strong>{t('settings.databaseReset')}</strong>
              <span className="sf-record-meta">{t('settings.databaseResetDesc')}</span>
            </div>
            <div className="sf-record-actions">
              <Button type="button" variant="danger" onClick={handleResetDb}>
                <Trash size={16} />
                {t('settings.resetDatabase')}
              </Button>
            </div>
          </li>
        </ul>
      </FormGroup>
    </>
  )
}
