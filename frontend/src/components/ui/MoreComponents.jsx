import React from 'react';

/**
 * Textarea - Simple textarea component
 */
export const Textarea = ({ label, error, className = '', ...props }) => {
  return (
    <div className="input-wrapper">
      {label && <label className="input-label">{label}</label>}
      <textarea 
        className={`input ${error ? 'input-error' : ''} ${className}`}
        style={{ minHeight: '80px', padding: '8px 10px', fontFamily: 'var(--font-mono)', resize: 'vertical' }}
        {...props}
      />
      {error && <div className="input-error-message">{error}</div>}
    </div>
  );
};

/**
 * NumberInput - Number input component
 */
export const NumberInput = ({ label, error, className = '', ...props }) => {
  return (
    <div className="input-wrapper">
      {label && <label className="input-label">{label}</label>}
      <input 
        type="number"
        className={`input ${error ? 'input-error' : ''} ${className}`}
        {...props}
      />
      {error && <div className="input-error-message">{error}</div>}
    </div>
  );
};

/**
 * Switch - Toggle switch component
 */
export const Switch = ({ label, checked, onChange, ...props }) => {
  return (
    <label className="switch-wrapper" style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange?.(e.target.checked)}
        style={{ accentColor: 'var(--accent-primary)' }}
        {...props}
      />
      {label && <span style={{ fontSize: '13px', color: 'var(--text-primary)' }}>{label}</span>}
    </label>
  );
};

/**
 * Radio - Radio button component
 */
export const Radio = ({ label, ...props }) => {
  return (
    <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
      <input type="radio" style={{ accentColor: 'var(--accent-primary)' }} {...props} />
      {label && <span style={{ fontSize: '13px', color: 'var(--text-primary)' }}>{label}</span>}
    </label>
  );
};

/**
 * Alert - Alert/notification box
 */
export const Alert = ({ title, children, color = 'info', className = '', ...props }) => {
  const colorMap = {
    info: 'alert-info',
    success: 'alert-success',
    warning: 'alert-warning',
    error: 'alert-error'
  };

  return (
    <div className={`alert ${colorMap[color]} ${className}`} {...props}>
      {title && <div className="alert-title">{title}</div>}
      <div className="alert-content">{children}</div>
    </div>
  );
};

/**
 * Box - Simple div wrapper
 */
export const Box = ({ children, className = '', ...props }) => {
  return <div className={className} {...props}>{children}</div>;
};
