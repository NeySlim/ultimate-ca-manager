import React, { useEffect } from 'react';
import { createPortal } from 'react-dom';
import styles from './Drawer.module.css';

export function Drawer({ isOpen, onClose, position = 'right', title, children }) {
  useEffect(() => {
    if (!isOpen) return;
    const handleEsc = (e) => e.key === 'Escape' && onClose?.();
    document.addEventListener('keydown', handleEsc);
    return () => document.removeEventListener('keydown', handleEsc);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return createPortal(
    <div className={styles.backdrop} onClick={onClose}>
      <div className={`${styles.drawer} ${styles[position]}`} onClick={(e) => e.stopPropagation()}>
        {title && (
          <div className={styles.header}>
            <h2 className={styles.title}>{title}</h2>
            <button className={styles.close} onClick={onClose}>×</button>
          </div>
        )}
        <div className={styles.body}>{children}</div>
      </div>
    </div>,
    document.body
  );
}
