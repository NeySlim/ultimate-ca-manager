import React, { useState } from 'react';
import { Copy, Check } from '@phosphor-icons/react';
import './CodeBlock.css';

/**
 * CodeBlock - Display code/certificates with copy functionality
 * Perfect for PEM certificates, keys, CSRs
 */
export const CodeBlock = ({
  code,
  language = 'text',
  maxHeight = '400px',
  showLineNumbers = false,
  className = '',
}) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  const lines = code.split('\n');

  return (
    <div className={`code-block ${className}`}>
      <div className="code-block-header">
        <span className="code-block-language">{language}</span>
        <button 
          className="code-block-copy-btn"
          onClick={handleCopy}
          title="Copy to clipboard"
        >
          {copied ? (
            <>
              <Check size={14} weight="bold" />
              Copied!
            </>
          ) : (
            <>
              <Copy size={14} />
              Copy
            </>
          )}
        </button>
      </div>
      <div className="code-block-content" style={{ maxHeight }}>
        {showLineNumbers ? (
          <table className="code-table">
            <tbody>
              {lines.map((line, idx) => (
                <tr key={idx}>
                  <td className="line-number">{idx + 1}</td>
                  <td className="line-content"><code>{line || '\u00A0'}</code></td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <pre><code>{code}</code></pre>
        )}
      </div>
    </div>
  );
};
