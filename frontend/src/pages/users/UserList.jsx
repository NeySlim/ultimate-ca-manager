import { useState, useMemo } from 'react';
import { DataTable } from '../../components/domain/DataTable';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { PageTopBar, PillFilter, PillFilters } from '../../components/common';
import { exportTableData } from '../../utils/export';
import { CreateUserModal } from '../../components/modals/CreateUserModal';
import { EditUserModal } from '../../components/modals/EditUserModal';
import { useUsers, useDeleteUser, useImportUsers, useResetUserPassword, useToggleUserStatus } from '../../hooks/useUsers';
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
  const [editingUser, setEditingUser] = useState(null);
  const [showEditModal, setShowEditModal] = useState(false);

  // Build API params from filters - memoized to prevent infinite re-renders
  const params = useMemo(() => {
    const p = {};
    if (roleFilter !== 'All') p.role = roleFilter.toLowerCase();
    if (statusFilter !== 'All') p.active = statusFilter === 'Active';
    return p;
  }, [roleFilter, statusFilter]);

  // Fetch users from backend
  const { data, isLoading, error } = useUsers(params);
  const deleteUser = useDeleteUser();
  const importUsers = useImportUsers();
  const resetPassword = useResetUserPassword();
  const toggleStatus = useToggleUserStatus();

  // Transform backend data to frontend format
  const getInitials = (name) => {
    if (!name) return '??';
    const parts = name.split(' ');
    return parts.length > 1 ? `${parts[0][0]}${parts[1][0]}` : name.substring(0, 2);
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return 'Never';
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);
    
    if (diffMins < 60) return `${diffMins} min ago`;
    if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
    if (diffDays < 7) return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;
    if (diffDays < 30) return `${Math.floor(diffDays / 7)} week${Math.floor(diffDays / 7) > 1 ? 's' : ''} ago`;
    return date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
  };

  // Transform backend data to frontend format
  // Handle both {data: [...]} and [...] formats
  const rawUsers = Array.isArray(data) ? data : (data?.data || []);
  
  const usersData = rawUsers.map(user => ({
    id: user.id,
    name: user.username,
    initials: getInitials(user.username),
    email: user.email,
    role: user.role ? (user.role.charAt(0).toUpperCase() + user.role.slice(1)) : 'Unknown',
    status: user.active ? 'Active' : 'Disabled',
    lastLogin: formatDate(user.last_login),
    created: formatDate(user.created_at),
  }));

  const filteredUsers = usersData;

  const adminCount = usersData.filter(u => u.role === 'Admin').length;
  const operatorCount = usersData.filter(u => u.role === 'Operator').length;
  const viewerCount = usersData.filter(u => u.role === 'Viewer').length;
  const activeCount = usersData.filter(u => u.status === 'Active').length;
  const disabledCount = usersData.filter(u => u.status === 'Disabled').length;

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

  const handleDelete = (user) => {
    if (confirm(`Delete user "${user.name}"?`)) {
      deleteUser.mutate(user.id);
    }
  };

  const handleImport = (e) => {
    const file = e.target.files[0];
    if (file) {
      importUsers.mutate(file);
      e.target.value = ''; // Reset input
    }
  };

  const handleEdit = (user) => {
    setEditingUser(user);
    setShowEditModal(true);
  };

  const handleResetPassword = (user) => {
    const newPassword = prompt(`Enter new password for ${user.name}:`);
    if (newPassword && newPassword.length >= 8) {
      resetPassword.mutate({ userId: user.id, newPassword });
    } else if (newPassword) {
      toast.error('Password must be at least 8 characters');
    }
  };

  const handleToggleStatus = (user) => {
    const action = user.status === 'Active' ? 'deactivate' : 'activate';
    if (confirm(`Are you sure you want to ${action} user "${user.name}"?`)) {
      toggleStatus.mutate(user.id);
    }
  };

  if (error) {
    return (
      <div className={styles.userList}>
        <PageTopBar icon="ph ph-users" title="Users" badge={<Badge variant="danger">Error</Badge>} />
        <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--color-danger)' }}>
          Error loading users: {error.message}
        </div>
      </div>
    );
  }

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
          <Button 
            variant="default" 
            size="sm" 
            icon="ph ph-pencil-simple" 
            onClick={(e) => { e.stopPropagation(); handleEdit(row); }} 
          />
          <Button 
            variant="default" 
            size="sm" 
            icon="ph ph-trash" 
            onClick={(e) => { e.stopPropagation(); handleDelete(row); }} 
          />
          <div style={{ position: 'relative', display: 'inline-block' }}>
            <Button 
              variant="default" 
              size="sm" 
              icon="ph ph-dots-three-outline-vertical" 
              onClick={(e) => { 
                e.stopPropagation(); 
                const menu = e.currentTarget.nextSibling;
                menu.style.display = menu.style.display === 'block' ? 'none' : 'block';
              }} 
            />
            <div 
              style={{
                display: 'none',
                position: 'absolute',
                right: 0,
                top: '100%',
                marginTop: '4px',
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border-primary)',
                borderRadius: 'var(--radius)',
                boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
                zIndex: 1000,
                minWidth: '160px',
              }}
            >
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  handleResetPassword(row);
                  e.currentTarget.parentElement.style.display = 'none';
                }}
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  fontSize: '13px',
                  color: 'var(--text-primary)',
                  background: 'transparent',
                  border: 'none',
                  textAlign: 'left',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                }}
                onMouseEnter={(e) => e.currentTarget.style.background = 'var(--bg-hover)'}
                onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
              >
                <i className="ph ph-key" />
                Reset Password
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  handleToggleStatus(row);
                  e.currentTarget.parentElement.style.display = 'none';
                }}
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  fontSize: '13px',
                  color: 'var(--text-primary)',
                  background: 'transparent',
                  border: 'none',
                  textAlign: 'left',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                }}
                onMouseEnter={(e) => e.currentTarget.style.background = 'var(--bg-hover)'}
                onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
              >
                <i className={row.status === 'Active' ? 'ph ph-prohibit' : 'ph ph-check-circle'} />
                {row.status === 'Active' ? 'Deactivate' : 'Activate'}
              </button>
            </div>
          </div>
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
            <input type="file" id="import-users" accept=".csv" style={{ display: 'none' }} onChange={handleImport} />
            <Button variant="default" icon="ph ph-upload-simple" onClick={() => document.getElementById('import-users').click()}>Import</Button>
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
          loading={isLoading}
          onRowClick={(row) => console.log('User clicked:', row)}
          pageSize={10}
        />
      </div>
      
      <CreateUserModal 
        isOpen={showCreateModal} 
        onClose={() => setShowCreateModal(false)} 
      />
      <EditUserModal 
        isOpen={showEditModal} 
        onClose={() => setShowEditModal(false)} 
        user={editingUser}
      />
    </div>
  );
}

export default UserList;
