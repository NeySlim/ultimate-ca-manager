import React, { useState, useEffect, useCallback } from 'react';
import { X, Export, ArrowsClockwise, Trash } from '@phosphor-icons/react';
import { useSelection } from '../../../core/context/SelectionContext';

const DEFAULT_WIDTH = 320;
const MAX_WIDTH_PERCENT = 1.3; // +30%

const PreviewPanel = () => {
  const { selectedItem, setSelectedItem } = useSelection();
  const [width, setWidth] = useState(DEFAULT_WIDTH);
  const [isResizing, setIsResizing] = useState(false);

  // Resize Handlers
  const handleMouseDown = (e) => {
    e.preventDefault();
    setIsResizing(true);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  };

  const handleMouseMove = useCallback((e) => {
    if (!isResizing) return;
    
    // Calculate new width (from right edge of window)
    const newWidth = document.body.clientWidth - e.clientX;
    
    // Constrain width
    const minWidth = DEFAULT_WIDTH;
    const maxWidth = DEFAULT_WIDTH * MAX_WIDTH_PERCENT;
    
    if (newWidth >= minWidth && newWidth <= maxWidth) {
      setWidth(newWidth);
    }
  }, [isResizing]);

  const handleMouseUp = useCallback(() => {
    setIsResizing(false);
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  }, []);

  useEffect(() => {
    if (isResizing) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
    }
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isResizing, handleMouseMove, handleMouseUp]);


  if (!selectedItem) {
    return (
      <div className="preview-panel" style={{ width: `${width}px`, alignItems: 'center', justifyContent: 'center', color: 'var(--text-secondary)' }}>
        <div 
            className={`preview-resize-handle ${isResizing ? 'active' : ''}`}
            onMouseDown={handleMouseDown}
        />
        <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 'var(--icon-size-xl)', marginBottom: 'var(--spacing-lg)', opacity: 0.2 }}>👆</div>
            <p style={{ fontSize: 'var(--font-size-ui)' }}>Select an item to view details</p>
        </div>
      </div>
    );
  }

  return (
    <div className="preview-panel" style={{ width: `${width}px` }}>
      {/* Resize Handle */}
      <div 
        className={`preview-resize-handle ${isResizing ? 'active' : ''}`}
        onMouseDown={handleMouseDown}
      />

      {/* Header */}
      <div className="panel-header" style={{
        height: '48px', padding: '0 var(--spacing-lg)', borderBottom: '1px solid var(--border-color)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        fontWeight: 600, fontSize: 'var(--font-size-ui)', color: 'var(--text-primary)'
      }}>
        <span>{selectedItem.type || 'Item'} Details</span>
        <button 
          onClick={() => setSelectedItem(null)}
          style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer' }}
        >
          <X size={14} />
        </button>
      </div>
      
      {/* Content */}
      <div className="panel-content" style={{ padding: 'var(--spacing-lg)', overflowY: 'auto', flex: 1 }}>
        
        {/* Main Info */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: 'var(--spacing-lg) 0 var(--spacing-xl) 0', borderBottom: '1px solid var(--border-color)', marginBottom: 'var(--spacing-lg)' }}>
             <div style={{ 
               width: '64px', height: '64px', fontSize: '24px', marginBottom: 'var(--spacing-md)',
               background: 'linear-gradient(135deg, var(--accent-primary), var(--accent-secondary))', borderRadius: 'var(--radius)',
               display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'white'
             }}>
               {selectedItem.avatar || selectedItem.name?.substring(0,2).toUpperCase() || 'IT'}
             </div>
             <div style={{ fontWeight: 600, fontSize: 'var(--font-size-lg)', marginBottom: 'var(--spacing-xs)', color: 'var(--text-primary)' }}>
               {selectedItem.title || selectedItem.name}
             </div>
             <div style={{ color: 'var(--text-secondary)', fontSize: 'var(--font-size-ui)' }}>
               {selectedItem.subtitle || 'No description'}
             </div>
        </div>

        {/* Dynamic Properties */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--spacing-lg)' }}>
        {Object.entries(selectedItem).map(([key, value]) => {
           if (['id', 'name', 'title', 'subtitle', 'avatar', 'type', 'children'].includes(key)) return null;
           // Skip empty values or complex objects for now
           if (value === null || value === undefined || typeof value === 'object') return null;
           
           return (
             <div key={key} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--spacing-xs)', fontSize: 'var(--font-size-mono)' }}>
               <div style={{ color: 'var(--text-secondary)', textTransform: 'uppercase', fontSize: 'var(--font-size-label)', fontWeight: 600, letterSpacing: '0.5px' }}>
                 {key.replace(/_/g, ' ').replace(/([A-Z])/g, ' $1').trim()}
               </div>
               <div style={{ color: 'var(--text-primary)', wordBreak: 'break-word', lineHeight: '1.4', background: 'var(--bg-app)', padding: 'var(--spacing-xs) var(--spacing-sm)', borderRadius: 'var(--radius)', border: '1px solid var(--border-color)' }}>
                 {String(value)}
               </div>
             </div>
           );
        })}
        </div>
        
        {/* Actions based on type */}
        <div style={{ marginTop: 'var(--spacing-xl)', display: 'flex', flexDirection: 'column', gap: 'var(--spacing-sm)' }}>
            {selectedItem.type === 'Certificate' && (
                <>
                    <button style={{ padding: 'var(--spacing-sm)', background: 'var(--bg-element)', border: '1px solid var(--border-color)', color: 'var(--text-primary)', borderRadius: 'var(--radius)', cursor: 'pointer', fontSize: 'var(--font-size-ui)', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 'var(--spacing-sm)' }}>
                      <Export size={16} /> Download PEM
                    </button>
                    <button style={{ padding: 'var(--spacing-sm)', background: 'var(--bg-element)', border: '1px solid var(--border-color)', color: 'var(--text-primary)', borderRadius: 'var(--radius)', cursor: 'pointer', fontSize: 'var(--font-size-ui)', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 'var(--spacing-sm)' }}>
                      <ArrowsClockwise size={16} /> Renew
                    </button>
                </>
            )}
            
            <button style={{ padding: 'var(--spacing-sm)', background: 'rgba(231, 115, 115, 0.1)', border: '1px solid rgba(231, 115, 115, 0.2)', color: 'var(--status-error)', borderRadius: 'var(--radius)', cursor: 'pointer', fontSize: 'var(--font-size-ui)', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 'var(--spacing-sm)' }}>
              <Trash size={16} /> {selectedItem.type === 'CA' ? 'Delete CA' : 'Revoke'}
            </button>
        </div>

      </div>
    </div>
  );
};

export default PreviewPanel;
