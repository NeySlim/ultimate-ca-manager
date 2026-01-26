import React, { Fragment } from 'react';
import { Listbox, Transition } from '@headlessui/react';
import { CaretDown, Check } from '@phosphor-icons/react';
import './Select.css';

/**
 * Select component - Headless UI Listbox
 * Replaces Mantine Select
 */
export const Select = ({ 
  value, 
  onChange, 
  options = [],
  placeholder = 'Select option',
  label,
  error,
  disabled = false
}) => {
  const selected = options.find(opt => opt.value === value);

  return (
    <div className="select-wrapper">
      {label && <label className="select-label">{label}</label>}
      
      <Listbox value={value} onChange={onChange} disabled={disabled}>
        <div className="select-container">
          <Listbox.Button className={`select-button ${error ? 'select-error' : ''}`}>
            <span className="select-value">
              {selected?.label || placeholder}
            </span>
            <CaretDown size={16} className="select-icon" />
          </Listbox.Button>

          <Transition
            as={Fragment}
            enter="select-transition-enter"
            enterFrom="select-transition-enter-from"
            enterTo="select-transition-enter-to"
            leave="select-transition-leave"
            leaveFrom="select-transition-leave-from"
            leaveTo="select-transition-leave-to"
          >
            <Listbox.Options className="select-dropdown">
              {options.map((option) => (
                <Listbox.Option
                  key={option.value}
                  value={option.value}
                  disabled={option.disabled}
                  as={Fragment}
                >
                  {({ active, selected }) => (
                    <li className={`select-option ${active ? 'select-option-active' : ''} ${selected ? 'select-option-selected' : ''}`}>
                      <span className="select-option-label">{option.label}</span>
                      {selected && <Check size={16} className="select-option-check" />}
                    </li>
                  )}
                </Listbox.Option>
              ))}
            </Listbox.Options>
          </Transition>
        </div>
      </Listbox>

      {error && <div className="select-error-message">{error}</div>}
    </div>
  );
};
