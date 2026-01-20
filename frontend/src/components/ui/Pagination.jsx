import React from 'react';
import { CaretLeft, CaretRight } from '@phosphor-icons/react';
import './Pagination.css';

/**
 * Pagination component - Custom implementation
 * Replaces Mantine Pagination
 */
export const Pagination = ({ 
  total = 1, 
  page = 1, 
  onChange,
  siblings = 1
}) => {
  const pages = [];
  const totalPages = Math.max(1, total);

  // Generate page numbers
  const startPage = Math.max(1, page - siblings);
  const endPage = Math.min(totalPages, page + siblings);

  // First page
  if (startPage > 1) {
    pages.push(1);
    if (startPage > 2) pages.push('...');
  }

  // Middle pages
  for (let i = startPage; i <= endPage; i++) {
    pages.push(i);
  }

  // Last page
  if (endPage < totalPages) {
    if (endPage < totalPages - 1) pages.push('...');
    pages.push(totalPages);
  }

  return (
    <div className="pagination">
      <button
        className="pagination-button"
        onClick={() => onChange(page - 1)}
        disabled={page <= 1}
      >
        <CaretLeft size={16} />
      </button>

      {pages.map((pageNum, idx) => (
        pageNum === '...' ? (
          <span key={`ellipsis-${idx}`} className="pagination-ellipsis">...</span>
        ) : (
          <button
            key={pageNum}
            className={`pagination-button ${page === pageNum ? 'pagination-button-active' : ''}`}
            onClick={() => onChange(pageNum)}
          >
            {pageNum}
          </button>
        )
      ))}

      <button
        className="pagination-button"
        onClick={() => onChange(page + 1)}
        disabled={page >= totalPages}
      >
        <CaretRight size={16} />
      </button>
    </div>
  );
};
