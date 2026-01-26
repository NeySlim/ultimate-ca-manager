import React, { useEffect, useState } from 'react';
import styles from './SuccessCheckmark.module.css';

export function SuccessCheckmark({ size = 64, delay = 0 }) {
  const [show, setShow] = useState(false);
  
  useEffect(() => {
    const timer = setTimeout(() => setShow(true), delay);
    return () => clearTimeout(timer);
  }, [delay]);
  
  if (!show) return null;
  
  return (
    <div className={styles.wrapper} style={{ width: size, height: size }}>
      <svg className={styles.checkmark} viewBox="0 0 52 52">
        <circle className={styles.circle} cx="26" cy="26" r="25" fill="none" />
        <path className={styles.check} fill="none" d="M14.1 27.2l7.1 7.2 16.7-16.8" />
      </svg>
    </div>
  );
}
