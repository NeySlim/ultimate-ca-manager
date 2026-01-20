import React from 'react';
import './PageHeader.css';

/**
 * PageHeader Component
 * 
 * Standard sticky header for all pages.
 */
const PageHeader = ({ title, actions, breadcrumbs }) => {
  return (
    <div className="ui-page-header">
      <div className="ui-header-left">
        {title && <h2 className="ui-page-title">{title}</h2>}
      </div>
      
      {actions && (
        <div className="ui-header-actions">
          {actions}
        </div>
      )}
    </div>
  );
};

export default PageHeader;
