import React from 'react';
import './Widget.css';

/**
 * Widget Component
 * 
 * Standard container for content blocks in the Grid.
 * Provides the "card" look: border, background, shadow.
 */
const Widget = ({ children, title, actions, className = '', ...props }) => {
  return (
    <div className={`ui-widget ${className}`} {...props}>
      {(title || actions) && (
        <div className="ui-widget-header">
          {title && <h3 className="ui-widget-title">{title}</h3>}
          {actions && <div className="ui-widget-actions">{actions}</div>}
        </div>
      )}
      <div className="ui-widget-content">
        {children}
      </div>
    </div>
  );
};

export default Widget;
