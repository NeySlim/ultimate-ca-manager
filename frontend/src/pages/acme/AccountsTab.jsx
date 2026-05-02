import { useTranslation } from 'react-i18next'
import { Plus, Key } from '@phosphor-icons/react'
import { Button, ResponsiveDataTable } from '../../components'

export default function AccountsTab({ accounts, selectedAccount, columns, searchQuery, onSearch, onSelectAccount, page, perPage, onPageChange, onPerPageChange, canWrite, onShowCreateModal }) {
  const { t } = useTranslation()

  return (
    <ResponsiveDataTable
      data={accounts}
      columns={columns}
      searchable
      searchPlaceholder={t('acme.searchAccounts')}
      onSearch={onSearch}
      onRowClick={onSelectAccount}
      selectedRow={selectedAccount}
      getRowId={(row) => row.id}
      pagination={{
        page,
        total: accounts.length,
        perPage,
        onChange: onPageChange,
        onPerPageChange: (v) => { onPerPageChange(v) }
      }}
      emptyState={{
        icon: Key,
        title: t('acme.noAccounts'),
        description: searchQuery ? t('acme.noMatchingAccounts') : t('acme.noAccountsDesc'),
        action: !searchQuery && canWrite && (
          <Button type="button" onClick={onShowCreateModal}>
            <Plus size={14} />
            {t('acme.createAccount')}
          </Button>
        )
      }}
    />
  )
}
