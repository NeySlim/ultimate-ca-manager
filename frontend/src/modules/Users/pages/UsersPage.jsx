import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Users as UsersIcon, Plus } from '@phosphor-icons/react';
import { Button, Stack, Card, Text, Loader, StatusBadge, SearchToolbar } from '../../../components/ui';
import { userService } from '../services/user.service';
import '../../../styles/common-page.css';

const UsersPage = () => {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    loadUsers();
  }, []);

  const loadUsers = async () => {
    try {
      setLoading(true);
      const data = await userService.getAll();
      setUsers(data.users || []);
    } catch (error) {
      console.error('Failed to load users:', error);
    } finally {
      setLoading(false);
    }
  };

  const filteredUsers = users.filter(user =>
    user.username?.toLowerCase().includes(search.toLowerCase()) ||
    user.email?.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="page-container">
      <div className="page-header">
        <div className="page-header-left">
          <UsersIcon size={28} weight="duotone" className="icon-gradient" />
          <div>
            <h1 className="page-title">Users</h1>
            <Text className="page-subtitle">{users.length} user(s) total</Text>
          </div>
        </div>
        <Button variant="primary" onClick={() => navigate('/users/create')}>
          <Plus size={16} weight="bold" />
          Create User
        </Button>
      </div>

      <SearchToolbar
        placeholder="Search users..."
        value={search}
        onChange={setSearch}
      />

      {loading ? (
        <div className="loading-center"><Loader /></div>
      ) : filteredUsers.length === 0 ? (
        <Card className="empty-state-card">
          <UsersIcon size={48} weight="thin" className="empty-icon" />
          <Text className="empty-text">No users found</Text>
          <Button variant="primary" onClick={() => navigate('/users/create')}>Create First User</Button>
        </Card>
      ) : (
        <Stack>
          {filteredUsers.map(user => (
            <Card key={user.uid} className="list-item-card" onClick={() => navigate(`/users/${user.uid}`)}>
              <div className="list-item-content">
                <div className="list-item-icon">
                  <UsersIcon size={32} weight="duotone" className="icon-gradient" />
                </div>
                <div className="list-item-details">
                  <Text className="list-item-title">{user.username}</Text>
                  <Text className="list-item-subtitle">{user.email}</Text>
                </div>
                <div className="list-item-badges">
                  <StatusBadge status={user.role} context="user" />
                  <StatusBadge status={user.active ? 'active' : 'disabled'} context="user" />
                </div>
              </div>
            </Card>
          ))}
        </Stack>
      )}
    </div>
  );
};

export default UsersPage;
