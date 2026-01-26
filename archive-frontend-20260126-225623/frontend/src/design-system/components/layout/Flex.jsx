import React from 'react';
import styles from './Flex.module.css';

export function Flex({ children, direction = 'row', gap = 'md', align = 'stretch', justify = 'flex-start', className }) {
  return <div className={`${styles.flex} ${styles[direction]} ${styles['gap' + gap]} ${styles['align' + align]} ${styles['justify' + justify]} ${className || ''}`}>{children}</div>;
}
