import { classNames } from '../../utils/classNames';
import { Icon } from '../ui/Icon';
import { AnimatedCounter } from '../ui/AnimatedCounter';
import styles from './StatCard.module.css';

/**
 * StatCard Component
 * 
 * Dashboard widget for statistics display
 * 
 * Features:
 * - Value with optional gradient
 * - Label (uppercase, muted)
 * - Sublabel (additional context)
 * - Icon (background, opacity 0.3)
 * - Optional trend indicator with text
 * - Variant for warning/error states
 * 
 * Design reference: prototype-dashboard.html .widget
 */
export function StatCard({ 
  value, 
  label,
  sublabel,
  icon, 
  gradient = true,
  trend,
  variant,
  cols = 3,
  className 
}) {
  const trendPositive = trend?.positive ?? (trend?.direction === 'up');
  const trendNegative = trend?.positive === false || trend?.direction === 'down';

  return (
    <div 
      className={classNames(styles.widget, className)}
      data-cols={cols}
      data-variant={variant}
    >
      <div className={styles.widgetHeader}>
        <div>
          <div className={styles.widgetTitle}>{label}</div>
          <div className={classNames(
            styles.widgetValue,
            gradient && !variant && styles.gradient,
            variant && styles[variant]
          )}>
            <AnimatedCounter 
              value={parseInt(value) || 0} 
              duration={1200}
            />
          </div>
          {sublabel && (
            <div className={styles.widgetSublabel}>{sublabel}</div>
          )}
          {trend && (
            <div className={classNames(
              styles.statTrend,
              trendPositive && styles.positive,
              trendNegative && styles.negative
            )}>
              {trend.direction === 'up' && <Icon name="ph ph-arrow-up" size={12} />}
              {trend.direction === 'down' && <Icon name="ph ph-warning" size={12} />}
              <span>{trend.text}</span>
            </div>
          )}
        </div>
        {icon && (
          <Icon 
            name={icon} 
            size={32} 
            className={styles.widgetIcon}
          />
        )}
      </div>
    </div>
  );
}

export default StatCard;
