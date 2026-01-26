import React from 'react';
import { Link } from 'react-router-dom';
import styles from './Breadcrumbs.module.css';

export function Breadcrumbs({ items }) {
  return (
    <nav className={styles.breadcrumbs}>
      {items.map((item, idx) => (
        <React.Fragment key={idx}>
          {idx > 0 && <span className={styles.separator}>/</span>}
          {item.href ? (
            <Link to={item.href} className={styles.link}>{item.label}</Link>
          ) : (
            <span className={styles.current}>{item.label}</span>
          )}
        </React.Fragment>
      ))}
    </nav>
  );
}
