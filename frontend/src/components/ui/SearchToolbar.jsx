import React from 'react';
import { MagnifyingGlass, Funnel } from '@phosphor-icons/react';
import { Input } from './Input';
import { Button } from './Button';
import './SearchToolbar.css';

/**
 * SearchToolbar - Generic search and filter toolbar
 * Used across tables and lists
 */
export const SearchToolbar = ({
  placeholder = 'Search...',
  value = '',
  onChange,
  onSearch,
  filters,
  actions,
  className = '',
}) => {
  return (
    <div className={`search-toolbar ${className}`}>
      <div className="search-toolbar-left">
        {/* Search Input */}
        <div className="search-input-wrapper">
          <MagnifyingGlass size={16} className="search-icon" />
          <input
            type="text"
            className="search-input"
            placeholder={placeholder}
            value={value}
            onChange={(e) => onChange?.(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && onSearch?.()}
          />
        </div>

        {/* Filters */}
        {filters && filters.length > 0 && (
          <div className="search-filters">
            <Funnel size={16} weight="bold" />
            {filters.map((filter, idx) => (
              <React.Fragment key={idx}>{filter}</React.Fragment>
            ))}
          </div>
        )}
      </div>

      {/* Actions (e.g., Create button) */}
      {actions && (
        <div className="search-toolbar-right">
          {actions}
        </div>
      )}
    </div>
  );
};
