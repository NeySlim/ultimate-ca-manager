import React, { useState } from 'react';
import { ActionIcon } from './ActionIcon';

/**
 * CopyButton - Copy to clipboard with feedback
 */
export const CopyButton = ({ value, timeout = 2000 }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), timeout);
    } catch (err) {
      console.error('Copy failed:', err);
    }
  };

  return (
    <ActionIcon 
      onClick={handleCopy}
      title={copied ? 'Copied!' : 'Copy'}
      style={{ color: copied ? 'var(--success)' : 'var(--text-tertiary)' }}
    >
      {copied ? '✓' : '📋'}
    </ActionIcon>
  );
};

/**
 * Grid - CSS Grid layout
 */
export const Grid = ({ children, columns = 12, gutter = 'md', className = '', ...props }) => {
  const gutterMap = {
    xs: '4px',
    sm: '8px',
    md: '16px',
    lg: '24px',
    xl: '32px'
  };

  return (
    <div
      className={`grid ${className}`}
      style={{
        display: 'grid',
        gridTemplateColumns: `repeat(${columns}, 1fr)`,
        gap: gutterMap[gutter],
        ...props.style
      }}
      {...props}
    >
      {children}
    </div>
  );
};

/**
 * Grid.Col - Grid column
 */
export const GridCol = ({ children, span = 12, offset = 0, className = '', ...props }) => {
  return (
    <div
      className={`grid-col ${className}`}
      style={{
        gridColumn: `span ${span}`,
        marginLeft: offset > 0 ? `calc(${offset} * (100% / 12))` : undefined,
        ...props.style
      }}
      {...props}
    >
      {children}
    </div>
  );
};

Grid.Col = GridCol;
