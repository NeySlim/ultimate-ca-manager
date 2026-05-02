import { useTranslation } from 'react-i18next'
import { Plus, Trash, PencilSimple, GlobeHemisphereWest } from '@phosphor-icons/react'
import { Button, Badge, ResponsiveDataTable } from '../../components'

export default function LocalDomainsTab({ localDomains, cas, onAdd, onEdit, onDelete, canWrite, canDelete }) {
  const { t } = useTranslation()

  return (
    <ResponsiveDataTable
      data={localDomains}
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
          key: 'issuing_ca_name',
          label: t('acme.issuingCA'),
          sortable: true,
          render: (val) => (
            <span className="text-text-primary">{val || '-'}</span>
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
              {canWrite && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={(e) => { e.stopPropagation(); onEdit(row) }}
                  title={t('common.edit')}
                >
                  <PencilSimple size={14} />
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
      emptyState={{
        icon: GlobeHemisphereWest,
        title: t('acme.noLocalDomains'),
        description: t('acme.noLocalDomainsDesc'),
        action: canWrite ? (
          <Button type="button" onClick={onAdd}>
            <Plus size={14} />
            {t('acme.addDomain')}
          </Button>
        ) : null
      }}
      onRowClick={(row) => onEdit(row)}
    />
  )
}
