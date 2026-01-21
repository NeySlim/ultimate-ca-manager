import { classNames } from '../../utils/classNames';
import { Icon } from '../ui/Icon';
import styles from './StatCard.module.css';

/**
 * StatCard Component
 * 
 * Dashboard widget for statistics display
 * 
 * Features:
 * - Value with optional gradient
 * - Label (uppercase, muted)
 * - Icon (background, opacity 0.3)
 * - Optional trend indicator (+12%, -5%)
 * 
 * Design reference: prototype-dashboard.html .widget
 */
export function StatCard({ 
  value, 
  label, 
  icon, 
  gradient = true,
  trend,
  cols = 3,
  className 
}) {
  const trendPositive = trend && parseFloat(trend) > 0;
  const trendNegative = trend && parseFloat(trend) < 0;

  return (
    <div 
      className={classNames(styles.widget, className)}
      data-cols={cols}
    >
      <div className={styles.widgetHeader}>
        <div className={styles.widgetTitle}>{label}</div>
        {icon && (
          <Icon 
            name={icon} 
            size={24} 
            className={styles.widgetIcon}
          />
        )}
      </div>

      <div className={classNames(
        styles.widgetValue,
        gradient && styles.gradient
      )}>
        {value}
      </div>

      {label && (
        <div className={styles.widgetLabel}>{label}</div>
      )}

      {trend && (
        <div className={classNames(
          styles.statTrend,
          trendPositive && styles.positive,
          trendNegative && styles.negative
        )}>
          <Icon 
            name={trendPositive ? 'arrow-up' : 'arrow-down'} 
            size={12}
          />
          <span>{trend}</span>
        </div>
      )}
    </div>
  );
}

export default StatCard;
