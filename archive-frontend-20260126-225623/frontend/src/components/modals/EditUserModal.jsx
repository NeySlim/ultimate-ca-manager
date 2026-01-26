import { useState, useEffect } from 'react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import toast from 'react-hot-toast';
import { useUpdateUser } from '../../hooks/useUsers';

export function EditUserModal({ isOpen, onClose, user }) {
  const [formData, setFormData] = useState({
    email: '',
    fullName: '',
    role: 'operator',
    active: true,
  });

  const updateUser = useUpdateUser();

  useEffect(() => {
    if (user) {
      setFormData({
        email: user.email || '',
        fullName: user.name || '',
        role: user.role?.toLowerCase() || 'operator',
        active: user.status === 'Active',
      });
    }
  }, [user]);

  if (!user) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!formData.email) {
      toast.error('Email is required');
      return;
    }

    updateUser.mutate({
      id: user.id,
      email: formData.email,
      full_name: formData.fullName,
      role: formData.role,
      active: formData.active,
    }, {
      onSuccess: () => {
        onClose();
      },
    });
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="medium">
      <Modal.Header>
        <i className="ph ph-pencil-simple" style={{ marginRight: '8px' }} />
        Edit User: {user.name}
      </Modal.Header>

      <form onSubmit={handleSubmit}>
        <Modal.Body>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {/* Username (read-only) */}
            <div>
              <label style={{ 
                display: 'block', 
                fontSize: '13px', 
                fontWeight: 500, 
                color: 'var(--text-primary)', 
                marginBottom: '6px' 
              }}>
                Username
              </label>
              <input
                type="text"
                value={user.name}
                readOnly
                disabled
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  fontSize: '13px',
                  border: '1px solid var(--border-primary)',
                  borderRadius: 'var(--radius)',
                  background: 'var(--bg-tertiary)',
                  color: 'var(--text-tertiary)',
                  cursor: 'not-allowed',
                }}
              />
            </div>

            {/* Email */}
            <div>
              <label style={{ 
                display: 'block', 
                fontSize: '13px', 
                fontWeight: 500, 
                color: 'var(--text-primary)', 
                marginBottom: '6px' 
              }}>
                Email <span style={{ color: 'var(--status-danger)' }}>*</span>
              </label>
              <input
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  fontSize: '13px',
                  border: '1px solid var(--border-primary)',
                  borderRadius: 'var(--radius)',
                  background: 'var(--bg-primary)',
                  color: 'var(--text-primary)',
                }}
              />
            </div>

            {/* Full Name */}
            <div>
              <label style={{ 
                display: 'block', 
                fontSize: '13px', 
                fontWeight: 500, 
                color: 'var(--text-primary)', 
                marginBottom: '6px' 
              }}>
                Full Name
              </label>
              <input
                type="text"
                value={formData.fullName}
                onChange={(e) => setFormData({ ...formData, fullName: e.target.value })}
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  fontSize: '13px',
                  border: '1px solid var(--border-primary)',
                  borderRadius: 'var(--radius)',
                  background: 'var(--bg-primary)',
                  color: 'var(--text-primary)',
                }}
              />
            </div>

            {/* Role */}
            <div>
              <label style={{ 
                display: 'block', 
                fontSize: '13px', 
                fontWeight: 500, 
                color: 'var(--text-primary)', 
                marginBottom: '6px' 
              }}>
                Role
              </label>
              <select
                value={formData.role}
                onChange={(e) => setFormData({ ...formData, role: e.target.value })}
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  fontSize: '13px',
                  border: '1px solid var(--border-primary)',
                  borderRadius: 'var(--radius)',
                  background: 'var(--bg-primary)',
                  color: 'var(--text-primary)',
                }}
              >
                <option value="admin">Admin</option>
                <option value="operator">Operator</option>
                <option value="viewer">Viewer</option>
              </select>
            </div>

            {/* Active Status */}
            <div>
              <label style={{ 
                display: 'flex',
                alignItems: 'center',
                fontSize: '13px', 
                fontWeight: 500, 
                color: 'var(--text-primary)',
                cursor: 'pointer',
              }}>
                <input
                  type="checkbox"
                  checked={formData.active}
                  onChange={(e) => setFormData({ ...formData, active: e.target.checked })}
                  style={{ marginRight: '8px' }}
                />
                Active User
              </label>
            </div>
          </div>
        </Modal.Body>

        <Modal.Footer>
          <Modal.CloseButton onClick={onClose} disabled={updateUser.isPending}>
            Cancel
          </Modal.CloseButton>
          <Button 
            type="submit" 
            variant="primary" 
            icon="ph ph-check"
            disabled={updateUser.isPending}
          >
            {updateUser.isPending ? 'Saving...' : 'Save Changes'}
          </Button>
        </Modal.Footer>
      </form>
    </Modal>
  );
}
