import React from 'react';
import styles from './Pagination.module.css';

export function Pagination({ currentPage, totalPages, onPageChange, className }) {
  const pages = Array.from({ length: totalPages }, (_, i) => i + 1);
  
  return (
    <div className={`${styles.pagination} ${className || ''}`}>
      <button 
        className={styles.arrow} 
        onClick={() => onPageChange(currentPage - 1)}
        disabled={currentPage === 1}
      >
        ←
      </button>
      
      {pages.map(page => (
        <button
          key={page}
          className={`${styles.page} ${page === currentPage ? styles.active : ''}`}
          onClick={() => onPageChange(page)}
        >
          {page}
        </button>
      ))}
      
      <button 
        className={styles.arrow}
        onClick={() => onPageChange(currentPage + 1)}
        disabled={currentPage === totalPages}
      >
        →
      </button>
    </div>
  );
}
