import { useTranslation } from 'react-i18next'
import { Plus, Trash, Play, Gear, PlugsConnected, GlobeHemisphereWest } from '@phosphor-icons/react'
import { Button, Badge, Card, HelpCard, ResponsiveDataTable } from '../../components'

export default function DomainsTab({ acmeDomains, dnsProviders, cas, onAdd, onEdit, onDelete, onTest, canWrite, canDelete }) {
  const { t } = useTranslation()

  return (
    <div className="p-4 space-y-4">
      <HelpCard variant="info" title={t('acme.domainsHelp')} compact>
        {t('acme.domainsHelpDesc')}
      </HelpCard>

      {acmeDomains.length === 0 ? (
        <Card className="p-8 text-center">
          <GlobeHemisphereWest size={48} className="mx-auto text-text-tertiary mb-4" />
          <h3 className="text-lg font-medium text-text-primary mb-2">
            {t('acme.noDomainsYet')}
          </h3>
          <p className="text-sm text-text-secondary mb-4">
            {t('acme.noDomainsDesc')}
          </p>
          {canWrite && (
            <Button type="button" onClick={onAdd}>
              <Plus size={14} />
              {t('acme.addDomain')}
            </Button>
          )}
        </Card>
      ) : (
        <ResponsiveDataTable
          data={acmeDomains}
          columns={[
            {
              key: 'domain',
              label: t('acme.domain'),
              sortable: true,
              render: (val) => (
                <span className="font-mono text-sm">{val}</span>
              )
            },
            {
              key: 'dns_provider_name',
              label: t('acme.provider'),
              sortable: true,
              render: (val, row) => (
                <div className="flex items-center gap-2">
                  <PlugsConnected size={14} className="text-accent-primary" />
                  <span>{val || row.dns_provider_type}</span>
                </div>
              )
            },
            {
              key: 'issuing_ca_name',
              label: t('acme.issuingCA'),
              sortable: true,
              render: (val) => (
                <span className={val ? 'text-text-primary' : 'text-text-tertiary'}>
                  {val || t('acme.defaultCA')}
                </span>
              )
            },
            {
              key: 'is_wildcard_allowed',
              label: t('acme.wildcard'),
              render: (val) => (
                <Badge variant={val ? 'success' : 'secondary'}>
                  {val ? t('common.yes') : t('common.no')}
                </Badge>
              )
            },
            {
              key: 'auto_approve',
              label: t('acme.autoApprove'),
              render: (val) => (
                <Badge variant={val ? 'success' : 'warning'}>
                  {val ? t('common.auto') : t('common.manual')}
                </Badge>
              )
            },
            {
              key: 'actions',
              label: '',
              render: (_, row) => (
                <div className="flex items-center gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={(e) => { e.stopPropagation(); onTest(row) }}
                    title={t('acme.testDnsAccess')}
                  >
                    <Play size={14} />
                  </Button>
                  {canWrite && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={(e) => { e.stopPropagation(); onEdit(row) }}
                      title={t('common.edit')}
                    >
                      <Gear size={14} />
                    </Button>
                  )}
                  {canDelete && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={(e) => { e.stopPropagation(); onDelete(row) }}
                      title={t('common.delete')}
                      className="text-status-error hover:text-status-error"
                    >
                      <Trash size={14} />
                    </Button>
                  )}
                </div>
              )
            }
          ]}
          onRowClick={(row) => onEdit(row)}
          emptyMessage={t('acme.noDomains')}
        />
      )}
    </div>
  )
}
