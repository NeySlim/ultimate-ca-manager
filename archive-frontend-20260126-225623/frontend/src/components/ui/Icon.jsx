import { classNames } from '../../utils/classNames';

/**
 * Icon Component
 * Phosphor Icons wrapper with gradient support
 * 
 * Usage:
 *   <Icon name="certificate" />
 *   <Icon name="check-circle" gradient />
 *   <Icon name="warning" color="warning" />
 */
export function Icon({
  name,
  size = 16,
  weight = 'regular',
  gradient = false,
  color,
  className,
  ...props
}) {
  // Icon weight mapping to Phosphor classes
  const weights = {
    regular: 'ph',
    bold: 'ph-bold',
    light: 'ph-light',
    thin: 'ph-thin',
    fill: 'ph-fill',
  };
  
  const weightClass = weights[weight] || 'ph';
  
  // Color mapping
  const colorStyles = color ? {
    success: { color: 'var(--status-success)' },
    warning: { color: 'var(--status-warning)' },
    danger: { color: 'var(--status-danger)' },
    info: { color: 'var(--status-info)' },
    primary: { color: 'var(--text-primary)' },
    secondary: { color: 'var(--text-secondary)' },
    tertiary: { color: 'var(--text-tertiary)' },
    accent: { color: 'var(--accent-primary)' },
  }[color] : {};
  
  return (
    <i
      className={classNames(
        `${weightClass} ph-${name}`,
        gradient && 'icon-gradient',
        className
      )}
      style={{
        fontSize: `${size}px`,
        ...colorStyles,
        ...props.style,
      }}
      {...props}
    />
  );
}

export default Icon;
