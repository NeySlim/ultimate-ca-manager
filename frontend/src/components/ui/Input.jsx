import { classNames } from '../../utils/classNames';
import styles from './Input.module.css';
import { useState } from 'react';

/**
 * Input Component
 * 
 * Design: Height 30px (strict dashboard reference)
 * Types: text, password, email, number, tel, url, search
 */
export function Input({
  type = 'text',
  value,
  onChange,
  placeholder,
  disabled = false,
  error,
  label,
  required = false,
  icon,
  className,
  ...props
}) {
  const inputId = props.id || `input-${Math.random().toString(36).substr(2, 9)}`;
  
  return (
    <div className={classNames(styles.inputWrapper, className)}>
      {label && (
        <label htmlFor={inputId} className={styles.label}>
          {label}
          {required && <span className={styles.required}>*</span>}
        </label>
      )}
      
      <div className={styles.inputContainer}>
        {icon && <i className={`${icon} ${styles.inputIcon}`} />}
        
        <input
          id={inputId}
          type={type}
          value={value}
          onChange={onChange}
          placeholder={placeholder}
          disabled={disabled}
          required={required}
          className={classNames(
            styles.input,
            icon && styles.hasIcon,
            error && styles.error
          )}
          {...props}
        />
      </div>
      
      {error && <span className={styles.errorText}>{error}</span>}
    </div>
  );
}

/**
 * PasswordInput Component
 */
export function PasswordInput(props) {
  const [visible, setVisible] = useState(false);
  
  return (
    <div className={styles.passwordWrapper}>
      <Input type={visible ? 'text' : 'password'} {...props} />
      <button
        type="button"
        className={styles.passwordToggle}
        onClick={() => setVisible(!visible)}
        tabIndex={-1}
      >
        <i className={visible ? 'ph ph-eye-slash' : 'ph ph-eye'} />
      </button>
    </div>
  );
}

export default Input;
