import React, { useState } from 'react';
import styles from './Tooltip.module.css';

export function Tooltip({ children, content, position = 'top' }) {
  const [show, setShow] = useState(false);
  
  return (
    <div className={styles.wrapper} onMouseEnter={() => setShow(true)} onMouseLeave={() => setShow(false)}>
      {children}
      {show && <div className={`${styles.tooltip} ${styles[position]}`}>{content}</div>}
    </div>
  );
}
