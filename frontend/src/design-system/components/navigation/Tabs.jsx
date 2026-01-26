import React, { useState } from 'react';
import styles from './Tabs.module.css';

export function Tabs({ tabs, defaultTab, onChange }) {
  const [active, setActive] = useState(defaultTab || tabs[0]?.id);
  
  const handleClick = (id) => {
    setActive(id);
    onChange?.(id);
  };
  
  return (
    <div className={styles.tabs}>
      {tabs.map((tab) => (
        <button
          key={tab.id}
          className={`${styles.tab} ${active === tab.id ? styles.active : ''}`}
          onClick={() => handleClick(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
