import { DataTable } from '../../components/domain/DataTable';
import { SearchToolbar } from '../../components/domain/SearchToolbar';
import { Badge } from '../../components/ui/Badge';
import { getBadgeVariant } from '../../utils/getBadgeVariant';
import { getUsers } from '../../services/mockData';
import styles from './UserList.module.css';

/**
 * Users Page
 * 
 * User management with:
 * - User list table
 * - Role-based badges
 * - Status indicators
 */
export function UserList() {
  const users = getUsers();

  const columns = [
    {
      key: 'username',
      label: 'Username',
      sortable: true,
    },
    {
      key: 'email',
      label: 'Email',
      sortable: true,
    },
    {
      key: 'role',
      label: 'Role',
      sortable: true,
      render: (row) => (
        <Badge variant={getBadgeVariant('user-role', row.role)}>
          {row.role}
        </Badge>
      ),
    },
    {
      key: 'status',
      label: 'Status',
      sortable: true,
      render: (row) => (
        <Badge variant={getBadgeVariant('user-status', row.status)}>
          {row.status}
        </Badge>
      ),
    },
    {
      key: 'lastLogin',
      label: 'Last Login',
      sortable: true,
    },
    {
      key: 'createdAt',
      label: 'Created At',
      sortable: true,
    },
  ];

  const filters = [
    {
      label: 'Role',
      options: ['All Roles', 'Admin', 'Operator', 'Security', 'User'],
    },
    {
      label: 'Status',
      options: ['All Statuses', 'Active', 'Inactive', 'Locked'],
    },
  ];

  const actions = [
    { label: 'Create User', icon: 'ph ph-user-plus', variant: 'primary' },
    { label: 'Export List', icon: 'ph ph-download-simple', variant: 'default' },
  ];

  return (
    <div className={styles.userList}>
      <SearchToolbar
        placeholder="Search users..."
        filters={filters}
        actions={actions}
        onSearch={(query) => console.log('Search:', query)}
        onFilterChange={(filter, value) => console.log('Filter:', filter, value)}
      />
      
      <DataTable
        columns={columns}
        data={users}
        onRowClick={(row) => console.log('User clicked:', row)}
      />
    </div>
  );
}

export default UserList;
