import { classNames } from '../../utils/classNames';
import styles from './Badge.module.css';

/**
 * Badge Component
 * 
 * Variants (context-aware):
 * - success: Valid, active, approved
 * - warning: Expiring, pending, attention
 * - danger: Expired, revoked, rejected, critical
 * - info: Information, neutral status
 * - secondary: Default, inactive
 * 
 * Usage:
 *   <Badge variant="success">Valid</Badge>
 *   <Badge variant={getBadgeVariant('cert-status', cert.status)}>{cert.status}</Badge>
 */
export function Badge({
  children,
  variant = 'secondary',
  size = 'default',
  className,
  ...props
}) {
  return (
    <span
      className={classNames(
        styles.badge,
        styles[`badge-${variant}`],
        styles[`badge-${size}`],
        className
      )}
      {...props}
    >
      {children}
    </span>
  );
}

export default Badge;
