import React from 'react';
import './Input.css';

/**
 * Input component - Replaces Mantine TextInput
 * Uses design-system.html input styles
 */
export const Input = ({ 
  label,
  error,
  description,
  required = false,
  className = '',
  wrapperClassName = '',
  ...props
}) => {
  return (
    <div className={`input-wrapper ${wrapperClassName}`}>
      {label && (
        <label className="input-label">
          {label}
          {required && <span className="input-required">*</span>}
        </label>
      )}
      {description && (
        <div className="input-description">{description}</div>
      )}
      <input 
        className={`input ${error ? 'input-error' : ''} ${className}`}
        {...props}
      />
      {error && <div className="input-error-message">{error}</div>}
    </div>
  );
};

/**
 * PasswordInput component
 */
export const PasswordInput = ({ ...props }) => {
  const [visible, setVisible] = React.useState(false);
  
  return (
    <div className="password-input-wrapper">
      <Input 
        type={visible ? 'text' : 'password'}
        {...props}
      />
      <button
        type="button"
        className="password-toggle"
        onClick={() => setVisible(!visible)}
        tabIndex={-1}
      >
        {visible ? '👁️' : '👁️‍🗨️'}
      </button>
    </div>
  );
};
