import React, { useState, useRef, useEffect } from 'react';
import styles from './Popover.module.css';

export function Popover({ trigger, children, position = 'bottom' }) {
  const [show, setShow] = useState(false);
  const popoverRef = useRef(null);
  
  useEffect(() => {
    if (!show) return;
    const handleClickOutside = (e) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target)) {
        setShow(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [show]);

  return (
    <div className={styles.wrapper} ref={popoverRef}>
      <div onClick={() => setShow(!show)}>{trigger}</div>
      {show && <div className={`${styles.popover} ${styles[position]}`}>{children}</div>}
    </div>
  );
}
