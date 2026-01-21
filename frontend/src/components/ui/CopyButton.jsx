import React, { useState } from 'react';
import { Copy, Check } from '@phosphor-icons/react';
import { Button } from './Button';

/**
 * CopyButton - Button to copy text to clipboard with feedback
 */
export const CopyButton = ({ 
  value, 
  variant = 'default',
  size = 'sm',
  className = '',
  children,
  ...props 
}) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  return (
    <Button
      variant={copied ? 'success' : variant}
      size={size}
      onClick={handleCopy}
      className={className}
      {...props}
    >
      {copied ? (
        <>
          <Check size={14} weight="bold" />
          {children || 'Copied!'}
        </>
      ) : (
        <>
          <Copy size={14} />
          {children || 'Copy'}
        </>
      )}
    </Button>
  );
};
