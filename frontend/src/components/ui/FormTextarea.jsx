import React from 'react';
import styles from './FormTextarea.module.css';

const FormTextarea = ({
  label,
  id,
  name,
  value,
  onChange,
  placeholder,
  required = false,
  disabled = false,
  error,
  rows = 4,
  className,
  ...rest
}) => {
  const textareaId = id || `textarea-${name}`;
  const errorId = `${textareaId}-error`;

  return (
    <div className={`${styles.formGroup} ${className || ''}`}>
      {label && (
        <label htmlFor={textareaId} className={styles.label}>
          {label}
          {required && <span className={styles.required} aria-label="required">*</span>}
        </label>
      )}
      <textarea
        id={textareaId}
        name={name}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        required={required}
        disabled={disabled}
        rows={rows}
        className={`${styles.textarea} ${error ? styles.textareaError : ''}`}
        aria-invalid={error ? 'true' : 'false'}
        aria-describedby={error ? errorId : undefined}
        {...rest}
      />
      {error && (
        <span id={errorId} className={styles.errorMessage} role="alert">
          {error}
        </span>
      )}
    </div>
  );
};

export default FormTextarea;
