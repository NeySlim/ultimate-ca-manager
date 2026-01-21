import { classNames } from '../../utils/classNames';
import styles from './Button.module.css';

/**
 * Button Component
 * 
 * Variants:
 * - primary: Main actions (create, save, apply)
 * - success: Positive actions (approve, activate)
 * - danger: Destructive actions (delete, revoke)
 * - default: Neutral actions (cancel, close)
 * 
 * Design: Outline only, NO fill (strict dashboard reference)
 * Height: 26px (strict)
 * Font: 13px
 */
export function Button({
  children,
  variant = 'default',
  size = 'default',
  disabled = false,
  loading = false,
  icon,
  onClick,
  type = 'button',
  className,
  ...props
}) {
  return (
    <button
      type={type}
      className={classNames(
        styles.btn,
        styles[`btn-${variant}`],
        styles[`btn-${size}`],
        disabled && styles.disabled,
        loading && styles.loading,
        className
      )}
      disabled={disabled || loading}
      onClick={onClick}
      {...props}
    >
      {loading && <i className="ph ph-circle-notch" />}
      {!loading && icon && <i className={icon} />}
      {children}
    </button>
  );
}

export default Button;
