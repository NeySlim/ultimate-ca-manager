import { classNames } from '../../utils/classNames';
import { Icon } from '../ui/Icon';
import styles from './ActivityFeed.module.css';

/**
 * ActivityItem Component
 * 
 * Single activity entry with exact dashboard styling:
 * - bg-tertiary background (tinted per theme)
 * - padding: 6px 8px
 * - gap: 8px
 * - Icon + content (text + time)
 * 
 * Icon variants:
 * - gradient: PKI operations (cert-issued, ca-created, etc.)
 * - color: Status (success, warning, danger)
 */
export function ActivityItem({ icon, text, time, user, variant = 'default', gradient = false }) {
  const iconColor = {
    success: 'success',
    warning: 'warning',
    danger: 'danger',
    info: 'info',
  }[variant];

  return (
    <div className={styles.activityItem}>
      <div className={styles.activityIcon}>
        <Icon 
          name={icon} 
          size={14} 
          gradient={gradient} 
          color={!gradient && iconColor ? iconColor : undefined}
        />
      </div>
      
      <div className={styles.activityContent}>
        <div className={styles.activityText}>
          {text}
          {user && <span className={styles.activityUser}> · {user}</span>}
        </div>
        <div className={styles.activityTime}>{time}</div>
      </div>
    </div>
  );
}

/**
 * ActivityFeed Component
 * 
 * List of activity items
 * Dashboard reference: Recent Activity section
 */
export function ActivityFeed({ items = [], className }) {
  return (
    <div className={classNames(styles.activityList, className)}>
      {items.map((item, index) => (
        <ActivityItem key={index} {...item} />
      ))}
    </div>
  );
}

export default ActivityFeed;
