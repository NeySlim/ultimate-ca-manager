import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import styles from './Sidebar.module.css';

export function Sidebar({ items }) {
  const location = useLocation();
  
  return (
    <nav className={styles.sidebar}>
      {items.map((item) => (
        <Link
          key={item.path}
          to={item.path}
          className={`${styles.item} ${location.pathname === item.path ? styles.active : ''}`}
        >
          {item.icon && <span className={styles.icon}>{item.icon}</span>}
          <span className={styles.label}>{item.label}</span>
        </Link>
      ))}
    </nav>
  );
}
