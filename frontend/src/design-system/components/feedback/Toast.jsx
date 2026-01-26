import React, { useEffect } from 'react';
import { createPortal } from 'react-dom';
import styles from './Toast.module.css';

export function Toast({ isOpen, onClose, variant = 'info', duration = 3000, children }) {
  useEffect(() => {
    if (!isOpen || !onClose) return;
    const timer = setTimeout(onClose, duration);
    return () => clearTimeout(timer);
  }, [isOpen, onClose, duration]);

  if (!isOpen) return null;

  return createPortal(
    <div className={`${styles.toast} ${styles[variant]}`}>
      {children}
      {onClose && <button className={styles.close} onClick={onClose}>×</button>}
    </div>,
    document.body
  );
}
