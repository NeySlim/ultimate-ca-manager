import { useState } from 'react';
import { DataTable } from '../../components/domain/DataTable';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { PageTopBar, PillFilter, PillFilters } from '../../components/common';
import { exportTableData } from '../../utils/export';
import { CreateUserModal } from '../../components/modals/CreateUserModal';
import toast from 'react-hot-toast';
import styles from './UserList.module.css';

/**
 * Users Page
 * 
 * Reference: prototype-users.html
 * - TopBar with title badge + action buttons
 * - Filter pills (Role: All/Admin/Operator/Viewer, Status: All/Active/Disabled)
 * - Table with user avatars, role badges, status badges
 * - 23 users total (3 Admin, 8 Operator, 12 Viewer)
 */
export function UserList() {
  const [roleFilter, setRoleFilter] = useState('All');
  const [statusFilter, setStatusFilter] = useState('All');
  const [showCreateModal, setShowCreateModal] = useState(false);

  const handleExport = () => {
    if (filteredUsers.length === 0) {
      toast.error('No data to export');
      return;
    }
    exportTableData(filteredUsers, 'users-export', {
      format: 'csv',
      columns: ['id', 'name', 'email', 'role', 'status', 'lastLogin', 'created']
    });
    toast.success('Users exported successfully');
  };

  const usersData = [
    { id: 1, name: 'John Admin', initials: 'JA', email: 'admin@acme.com', role: 'Admin', status: 'Active', lastLogin: '2 min ago', created: 'Jan 2020' },
    { id: 2, name: 'Alice Root', initials: 'AR', email: 'alice.root@acme.com', role: 'Admin', status: 'Active', lastLogin: '1 hour ago', created: 'Mar 2020' },
    { id: 3, name: 'Security Team', initials: 'ST', email: 'security@acme.com', role: 'Admin', status: 'Active', lastLogin: '5 hours ago', created: 'Jun 2021' },
    { id: 4, name: 'Bob Operator', initials: 'BO', email: 'bob.ops@acme.com', role: 'Operator', status: 'Active', lastLogin: '10 min ago', created: 'Jan 2021' },
    { id: 5, name: 'Charlie Deploy', initials: 'CD', email: 'charlie@acme.com', role: 'Operator', status: 'Active', lastLogin: '30 min ago', created: 'Feb 2021' },
    { id: 6, name: 'David Cert', initials: 'DC', email: 'david.cert@acme.com', role: 'Operator', status: 'Active', lastLogin: '2 hours ago', created: 'Mar 2021' },
    { id: 7, name: 'Emma Manage', initials: 'EM', email: 'emma@acme.com', role: 'Operator', status: 'Active', lastLogin: '1 day ago', created: 'Apr 2021' },
    { id: 8, name: 'Frank PKI', initials: 'FP', email: 'frank.pki@acme.com', role: 'Operator', status: 'Active', lastLogin: '2 days ago', created: 'May 2021' },
    { id: 9, name: 'Grace Ops', initials: 'GO', email: 'grace@acme.com', role: 'Operator', status: 'Active', lastLogin: '3 days ago', created: 'Jun 2021' },
    { id: 10, name: 'Henry Sysadmin', initials: 'HS', email: 'henry@acme.com', role: 'Operator', status: 'Disabled', lastLogin: 'Never', created: 'Jul 2021' },
    { id: 11, name: 'Iris Deploy', initials: 'ID', email: 'iris.deploy@acme.com', role: 'Operator', status: 'Active', lastLogin: '1 week ago', created: 'Aug 2021' },
    { id: 12, name: 'Jack Viewer', initials: 'JV', email: 'jack.viewer@acme.com', role: 'Viewer', status: 'Active', lastLogin: '3 hours ago', created: 'Jan 2022' },
    { id: 13, name: 'Karen Read', initials: 'KR', email: 'karen@acme.com', role: 'Viewer', status: 'Active', lastLogin: '1 day ago', created: 'Feb 2022' },
    { id: 14, name: 'Leo Monitor', initials: 'LM', email: 'leo.monitor@acme.com', role: 'Viewer', status: 'Active', lastLogin: '2 days ago', created: 'Mar 2022' },
    { id: 15, name: 'Mona Track', initials: 'MT', email: 'mona@acme.com', role: 'Viewer', status: 'Active', lastLogin: '3 days ago', created: 'Apr 2022' },
    { id: 16, name: 'Nathan Log', initials: 'NL', email: 'nathan.log@acme.com', role: 'Viewer', status: 'Active', lastLogin: '4 days ago', created: 'May 2022' },
    { id: 17, name: 'Olivia Audit', initials: 'OA', email: 'olivia@acme.com', role: 'Viewer', status: 'Active', lastLogin: '5 days ago', created: 'Jun 2022' },
    { id: 18, name: 'Paul Check', initials: 'PC', email: 'paul.check@acme.com', role: 'Viewer', status: 'Active', lastLogin: '1 week ago', created: 'Jul 2022' },
    { id: 19, name: 'Quinn Report', initials: 'QR', email: 'quinn@acme.com', role: 'Viewer', status: 'Active', lastLogin: '1 week ago', created: 'Aug 2022' },
    { id: 20, name: 'Robert Stats', initials: 'RS', email: 'robert.stats@acme.com', role: 'Viewer', status: 'Active', lastLogin: '2 weeks ago', created: 'Sep 2022' },
    { id: 21, name: 'Sara Inactive', initials: 'SI', email: 'sara@acme.com', role: 'Viewer', status: 'Disabled', lastLogin: 'Never', created: 'Oct 2022' },
    { id: 22, name: 'Tom Access', initials: 'TA', email: 'tom.access@acme.com', role: 'Viewer', status: 'Disabled', lastLogin: 'Mar 2024', created: 'Nov 2022' },
    { id: 23, name: 'Uma Review', initials: 'UR', email: 'uma@acme.com', role: 'Viewer', status: 'Active', lastLogin: '3 weeks ago', created: 'Dec 2022' },
  ];

  const filteredUsers = usersData.filter(user => {
    if (roleFilter !== 'All' && user.role !== roleFilter) return false;
    if (statusFilter !== 'All' && user.status !== statusFilter) return false;
    return true;
  });

  const adminCount = usersData.filter(u => u.role === 'Admin').length;
  const operatorCount = usersData.filter(u => u.role === 'Operator').length;
  const viewerCount = usersData.filter(u => u.role === 'Viewer').length;
  const activeCount = usersData.filter(u => u.status === 'Active').length;
  const disabledCount = usersData.filter(u => u.status === 'Disabled').length;

  const columns = [
    {
      key: 'name',
      label: 'User',
      render: (row) => (
        <div className={styles.userInfoCell}>
          <div className={styles.userAvatar}>{row.initials}</div>
          <div className={styles.userDetails}>
            <div className={styles.userName}>{row.name}</div>
            <div className={styles.userEmail}>{row.email}</div>
          </div>
        </div>
      ),
    },
    {
      key: 'role',
      label: 'Role',
      render: (row) => {
        const variant = row.role === 'Admin' ? 'error' : row.role === 'Operator' ? 'warning' : 'info';
        return <Badge variant={variant}>{row.role}</Badge>;
      },
    },
    {
      key: 'status',
      label: 'Status',
      render: (row) => (
        <Badge variant={row.status === 'Active' ? 'success' : 'error'}>
          {row.status}
        </Badge>
      ),
    },
    {
      key: 'lastLogin',
      label: 'Last Login',
    },
    {
      key: 'created',
      label: 'Created',
    },
    {
      key: 'actions',
      label: 'Actions',
      render: (row) => (
        <div className={styles.actionsCell}>
          <Button variant="default" size="sm" icon="ph ph-pencil-simple" onClick={(e) => { e.stopPropagation(); console.log('Edit:', row); }} />
          <Button variant="default" size="sm" icon="ph ph-prohibit" onClick={(e) => { e.stopPropagation(); console.log('Disable:', row); }} />
          <Button variant="default" size="sm" icon="ph ph-dots-three-outline-vertical" onClick={(e) => { e.stopPropagation(); console.log('More:', row); }} />
        </div>
      ),
    },
  ];

  return (
    <div className={styles.userList}>
      <PageTopBar
        icon="ph ph-users"
        title="Users"
        badge={<Badge variant="info">{activeCount} Active</Badge>}
        actions={
          <>
            <Button variant="default" icon="ph ph-upload-simple">Import</Button>
            <Button variant="default" icon="ph ph-download-simple" onClick={handleExport}>Export</Button>
            <Button variant="primary" icon="ph ph-plus" onClick={() => setShowCreateModal(true)}>Create User</Button>
          </>
        }
      />

      <div className={styles.filtersSection}>
        <div className={styles.filterGroup}>
          <label>Role</label>
          <PillFilters>
            <PillFilter active={roleFilter === 'All'} onClick={() => setRoleFilter('All')}>
              All <span className={styles.badge}>({usersData.length})</span>
            </PillFilter>
            <PillFilter active={roleFilter === 'Admin'} onClick={() => setRoleFilter('Admin')}>
              Admin <span className={styles.badge}>({adminCount})</span>
            </PillFilter>
            <PillFilter active={roleFilter === 'Operator'} onClick={() => setRoleFilter('Operator')}>
              Operator <span className={styles.badge}>({operatorCount})</span>
            </PillFilter>
            <PillFilter active={roleFilter === 'Viewer'} onClick={() => setRoleFilter('Viewer')}>
              Viewer <span className={styles.badge}>({viewerCount})</span>
            </PillFilter>
          </PillFilters>
        </div>
        <div className={styles.filterGroup}>
          <label>Status</label>
          <PillFilters>
            <PillFilter active={statusFilter === 'All'} onClick={() => setStatusFilter('All')}>
              All <span className={styles.badge}>({usersData.length})</span>
            </PillFilter>
            <PillFilter active={statusFilter === 'Active'} onClick={() => setStatusFilter('Active')}>
              Active <span className={styles.badge}>({activeCount})</span>
            </PillFilter>
            <PillFilter active={statusFilter === 'Disabled'} onClick={() => setStatusFilter('Disabled')}>
              Disabled <span className={styles.badge}>({disabledCount})</span>
            </PillFilter>
          </PillFilters>
        </div>
      </div>

      <div className={styles.tableContainer}>
        <DataTable
          columns={columns}
          data={filteredUsers}
          onRowClick={(row) => console.log('User clicked:', row)}
          pageSize={10}
        />
      </div>
      
      <CreateUserModal 
        isOpen={showCreateModal} 
        onClose={() => setShowCreateModal(false)} 
      />
    </div>
  );
}

export default UserList;
