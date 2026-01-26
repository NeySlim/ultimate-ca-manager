import { Modal } from '../ui/Modal';
import { Badge } from '../ui/Badge';
import { getBadgeVariant } from '../../utils/getBadgeVariant';
import styles from './ViewUserDetailsModal.module.css';

export function ViewUserDetailsModal({ isOpen, onClose, user }) {
  if (!user) return null;

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="User Details"
      size="medium"
    >
      <div className={styles.container}>
        <div className={styles.header}>
          <div className={styles.avatar}>{user.initials}</div>
          <div className={styles.userInfo}>
            <h3 className={styles.name}>{user.name}</h3>
            <p className={styles.email}>{user.email}</p>
          </div>
        </div>

        <div className={styles.section}>
          <h4 className={styles.sectionTitle}>Account Information</h4>
          <div className={styles.grid}>
            <div className={styles.field}>
              <label>Role</label>
              <Badge variant={getBadgeVariant('user-role', user.role)}>{user.role}</Badge>
            </div>
            <div className={styles.field}>
              <label>Status</label>
              <Badge variant={user.status === 'Active' ? 'success' : 'danger'}>
                {user.status}
              </Badge>
            </div>
            <div className={styles.field}>
              <label>Last Login</label>
              <div className={styles.value}>{user.lastLogin || 'Never'}</div>
            </div>
            <div className={styles.field}>
              <label>Created</label>
              <div className={styles.value}>{user.created}</div>
            </div>
          </div>
        </div>

        {user.permissions && user.permissions.length > 0 && (
          <div className={styles.section}>
            <h4 className={styles.sectionTitle}>Permissions</h4>
            <div className={styles.permissions}>
              {user.permissions.map((perm, idx) => (
                <Badge key={idx} variant="info">{perm}</Badge>
              ))}
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}
