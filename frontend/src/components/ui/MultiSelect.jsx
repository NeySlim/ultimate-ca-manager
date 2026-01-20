import React, { useState } from 'react';
import { Listbox } from '@headlessui/react';
import './Select.css'; // Reuse Select styles

/**
 * MultiSelect - Multi-select dropdown using Headless UI Listbox
 * Allows selecting multiple values
 */
export const MultiSelect = ({ 
  data = [], 
  value = [], 
  onChange, 
  label, 
  placeholder = 'Select items...', 
  error,
  searchable = false,
  className = '',
  ...props 
}) => {
  const [query, setQuery] = useState('');

  // Filter options if searchable
  const filteredData = searchable && query
    ? data.filter(item => 
        (item.label || item.value).toLowerCase().includes(query.toLowerCase())
      )
    : data;

  // Get labels for selected values
  const getSelectedLabels = () => {
    if (!value || value.length === 0) return placeholder;
    return value
      .map(v => {
        const item = data.find(d => d.value === v);
        return item ? (item.label || item.value) : v;
      })
      .join(', ');
  };

  return (
    <div className={`input-wrapper ${className}`}>
      {label && <label className="input-label">{label}</label>}
      
      <Listbox value={value} onChange={onChange} multiple>
        <div className="select-container">
          <Listbox.Button className={`select-button ${error ? 'select-error' : ''}`}>
            <span className="select-value">{getSelectedLabels()}</span>
            <span className="select-arrow">▼</span>
          </Listbox.Button>

          <Listbox.Options className="select-options">
            {searchable && (
              <div className="select-search">
                <input
                  type="text"
                  className="input"
                  placeholder="Search..."
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onClick={(e) => e.stopPropagation()}
                />
              </div>
            )}

            {filteredData.length === 0 && (
              <div className="select-empty">No results found</div>
            )}

            {filteredData.map((item) => (
              <Listbox.Option
                key={item.value}
                value={item.value}
                className={({ active, selected }) =>
                  `select-option ${active ? 'select-option-active' : ''} ${selected ? 'select-option-selected' : ''}`
                }
              >
                {({ selected }) => (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <input 
                      type="checkbox" 
                      checked={selected} 
                      onChange={() => {}}
                      style={{ accentColor: 'var(--accent-primary)' }}
                    />
                    <span>{item.label || item.value}</span>
                  </div>
                )}
              </Listbox.Option>
            ))}
          </Listbox.Options>
        </div>
      </Listbox>

      {error && <div className="input-error-message">{error}</div>}
    </div>
  );
};
