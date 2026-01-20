import React from 'react';
import './SegmentedControl.css';

/**
 * SegmentedControl - Simple toggle component
 * Replaces Mantine SegmentedControl
 */
export const SegmentedControl = ({ value, onChange, data = [] }) => {
  return (
    <div className="segmented-control">
      {data.map((item) => (
        <button
          key={item.value}
          className={`segmented-button ${value === item.value ? 'segmented-button-active' : ''}`}
          onClick={() => onChange(item.value)}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
};
