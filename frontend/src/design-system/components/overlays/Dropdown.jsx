import React, { useState, useRef, useEffect } from 'react';
import styles from './Dropdown.module.css';

export function Dropdown({ trigger, items, onSelect }) {
  const [show, setShow] = useState(false);
  const dropdownRef = useRef(null);
  
  useEffect(() => {
    if (!show) return;
    const handleClickOutside = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setShow(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [show]);

  const handleItemClick = (item) => {
    onSelect?.(item);
    setShow(false);
  };

  return (
    <div className={styles.wrapper} ref={dropdownRef}>
      <div onClick={() => setShow(!show)}>{trigger}</div>
      {show && (
        <div className={styles.dropdown}>
          {items.map((item, idx) => (
            <div key={idx} className={styles.item} onClick={() => handleItemClick(item)}>
              {item.label}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
