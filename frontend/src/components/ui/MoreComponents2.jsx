import React from 'react';

/**
 * Avatar - User avatar component
 */
export const Avatar = ({ src, alt, size = 38, color, children, className = '', ...props }) => {
  const styles = {
    width: size,
    height: size,
    borderRadius: '50%',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: `${size / 2.5}px`,
    fontWeight: 600,
    backgroundColor: color || 'var(--accent-primary)',
    color: '#fff',
    overflow: 'hidden',
  };

  if (src) {
    return <img src={src} alt={alt} className={`avatar ${className}`} style={styles} {...props} />;
  }

  return (
    <div className={`avatar ${className}`} style={styles} {...props}>
      {children || alt?.[0]?.toUpperCase()}
    </div>
  );
};

/**
 * Title - Heading component
 */
export const Title = ({ children, order = 1, className = '', ...props }) => {
  const Tag = `h${order}`;
  const styles = {
    margin: 0,
    fontFamily: 'var(--font-sans)',
    fontWeight: 600,
    color: 'var(--text-primary)',
    lineHeight: 1.3,
  };

  return (
    <Tag className={`title ${className}`} style={styles} {...props}>
      {children}
    </Tag>
  );
};

/**
 * Anchor - Link component
 */
export const Anchor = ({ children, href, className = '', ...props }) => {
  return (
    <a
      href={href}
      className={`anchor ${className}`}
      style={{
        color: 'var(--accent-primary)',
        textDecoration: 'none',
        cursor: 'pointer',
      }}
      {...props}
    >
      {children}
    </a>
  );
};

/**
 * Loader - Loading spinner
 */
export const Loader = ({ size = 24, className = '', ...props }) => {
  return (
    <div
      className={`spinner ${className}`}
      style={{ width: size, height: size }}
      {...props}
    />
  );
};

/**
 * ScrollArea - Scrollable area
 */
export const ScrollArea = ({ children, className = '', style, ...props }) => {
  return (
    <div
      className={`scroll-area ${className}`}
      style={{
        overflow: 'auto',
        ...style
      }}
      {...props}
    >
      {children}
    </div>
  );
};

/**
 * ThemeIcon - Icon with background
 */
export const ThemeIcon = ({ children, color = 'primary', size = 38, radius = 'md', className = '', ...props }) => {
  const colorMap = {
    primary: 'var(--accent-primary)',
    success: 'var(--success)',
    warning: 'var(--warning)',
    error: 'var(--error)',
  };

  const radiusMap = {
    xs: '2px',
    sm: '4px',
    md: '6px',
    lg: '8px',
    xl: '12px',
  };

  return (
    <div
      className={`theme-icon ${className}`}
      style={{
        width: size,
        height: size,
        borderRadius: radiusMap[radius],
        backgroundColor: colorMap[color] || color,
        color: '#fff',
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: `${size / 2}px`,
      }}
      {...props}
    >
      {children}
    </div>
  );
};

/**
 * Table - Simple table wrapper
 */
export const Table = ({ children, className = '', ...props }) => {
  return (
    <table
      className={`table ${className}`}
      style={{
        width: '100%',
        borderCollapse: 'collapse',
      }}
      {...props}
    >
      {children}
    </table>
  );
};

Table.Thead = ({ children, ...props }) => <thead {...props}>{children}</thead>;
Table.Tbody = ({ children, ...props }) => <tbody {...props}>{children}</tbody>;
Table.Tr = ({ children, ...props }) => <tr {...props}>{children}</tr>;
Table.Th = ({ children, ...props }) => (
  <th style={{ padding: '8px 12px', textAlign: 'left', borderBottom: '1px solid var(--border-color)' }} {...props}>
    {children}
  </th>
);
Table.Td = ({ children, ...props }) => (
  <td style={{ padding: '8px 12px', borderBottom: '1px solid var(--border-color)' }} {...props}>
    {children}
  </td>
);

/**
 * Paper - Card-like container
 */
export const Paper = ({ children, withBorder = false, shadow, className = '', ...props }) => {
  return (
    <div
      className={`card ${className}`}
      style={{
        border: withBorder ? '1px solid var(--border-color)' : 'none',
        boxShadow: shadow ? 'var(--shadow-md)' : 'none',
      }}
      {...props}
    >
      {children}
    </div>
  );
};

/**
 * Stepper - Step indicator
 */
export const Stepper = ({ active, children, ...props }) => {
  return (
    <div className="stepper" {...props}>
      {React.Children.map(children, (child, index) =>
        React.cloneElement(child, {
          isActive: index === active,
          isCompleted: index < active,
        })
      )}
    </div>
  );
};

Stepper.Step = ({ label, description, isActive, isCompleted, ...props }) => {
  return (
    <div
      className={`stepper-step ${isActive ? 'active' : ''} ${isCompleted ? 'completed' : ''}`}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        padding: '12px',
        opacity: isActive || isCompleted ? 1 : 0.5,
      }}
      {...props}
    >
      <div
        style={{
          width: 32,
          height: 32,
          borderRadius: '50%',
          backgroundColor: isCompleted ? 'var(--success)' : isActive ? 'var(--accent-primary)' : 'var(--bg-tertiary)',
          color: '#fff',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: '14px',
          fontWeight: 600,
        }}
      >
        {isCompleted ? '✓' : '•'}
      </div>
      <div>
        <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>{label}</div>
        {description && <div style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>{description}</div>}
      </div>
    </div>
  );
};

/**
 * Center - Center content
 */
export const Center = ({ children, inline = false, className = '', ...props }) => {
  return (
    <div
      className={`center ${className}`}
      style={{
        display: inline ? 'inline-flex' : 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
      {...props}
    >
      {children}
    </div>
  );
};

/**
 * Code - Inline code display
 */
export const Code = ({ children, className = '', ...props }) => {
  return (
    <code
      className={`code ${className}`}
      style={{
        fontFamily: 'var(--font-mono)',
        fontSize: '0.9em',
        backgroundColor: 'var(--bg-tertiary)',
        color: 'var(--accent-primary)',
        padding: '2px 6px',
        borderRadius: '4px',
        border: '1px solid var(--border-color)',
      }}
      {...props}
    >
      {children}
    </code>
  );
};
