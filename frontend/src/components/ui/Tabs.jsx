import React, { Fragment } from 'react';
import { Tab as HeadlessTab } from '@headlessui/react';
import './Tabs.css';

/**
 * Tabs component - Headless UI Tab
 * Replaces Mantine Tabs
 */
export const Tabs = ({ children, defaultValue = 0, onChange }) => {
  const [selectedIndex, setSelectedIndex] = React.useState(defaultValue);

  const handleChange = (index) => {
    setSelectedIndex(index);
    if (onChange) onChange(index);
  };

  return (
    <HeadlessTab.Group selectedIndex={selectedIndex} onChange={handleChange}>
      {children}
    </HeadlessTab.Group>
  );
};

export const TabsList = ({ children }) => {
  return (
    <HeadlessTab.List className="tabs-list">
      {children}
    </HeadlessTab.List>
  );
};

export const TabsTab = ({ children, value }) => {
  return (
    <HeadlessTab as={Fragment}>
      {({ selected }) => (
        <button className={`tabs-tab ${selected ? 'tabs-tab-active' : ''}`}>
          {children}
        </button>
      )}
    </HeadlessTab>
  );
};

export const TabsPanels = ({ children }) => {
  return (
    <HeadlessTab.Panels className="tabs-panels">
      {children}
    </HeadlessTab.Panels>
  );
};

export const TabsPanel = ({ children }) => {
  return (
    <HeadlessTab.Panel className="tabs-panel">
      {children}
    </HeadlessTab.Panel>
  );
};
