import React from 'react';
import { X, Export, ArrowsClockwise, Copy, Trash } from '@phosphor-icons/react';
import { useSelection } from '../../../core/context/SelectionContext';

const PreviewPanel = () => {
  const { selectedItem, setSelectedItem } = useSelection();

  if (!selectedItem) {
    return (
      <div className="preview-panel" style={{ alignItems: 'center', justifyContent: 'center', color: '#909296' }}>
        <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '48px', marginBottom: '16px', opacity: 0.2 }}>👆</div>
            <p style={{ fontSize: '13px' }}>Select an item to view details</p>
        </div>
      </div>
    );
  }

  return (
    <div className="preview-panel">
      {/* Header */}
      <div className="panel-header" style={{
        height: '48px', padding: '0 16px', borderBottom: '1px solid #373a40',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        fontWeight: 600, fontSize: '13px', color: '#c1c2c5'
      }}>
        <span>{selectedItem.type || 'Item'} Details</span>
        <button 
          onClick={() => setSelectedItem(null)}
          style={{ background: 'none', border: 'none', color: '#909296', cursor: 'pointer' }}
        >
          <X size={14} />
        </button>
      </div>
      
      {/* Content */}
      <div className="panel-content" style={{ padding: '16px', overflowY: 'auto', flex: 1 }}>
        
        {/* Main Info */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '16px 0 24px 0', borderBottom: '1px solid #373a40', marginBottom: '16px' }}>
             <div style={{ 
               width: '64px', height: '64px', fontSize: '24px', marginBottom: '12px',
               background: 'linear-gradient(135deg, #5a8fc7, #7aa5d9)', borderRadius: '3px',
               display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'white'
             }}>
               {selectedItem.avatar || selectedItem.name?.substring(0,2).toUpperCase() || 'IT'}
             </div>
             <div style={{ fontWeight: 600, fontSize: '16px', marginBottom: '4px', color: '#e0e0e0' }}>
               {selectedItem.title || selectedItem.name}
             </div>
             <div style={{ color: '#909296', fontSize: '13px' }}>
               {selectedItem.subtitle || 'No description'}
             </div>
        </div>

        {/* Dynamic Properties */}
        {Object.entries(selectedItem).map(([key, value]) => {
           if (['id', 'name', 'title', 'subtitle', 'avatar', 'type'].includes(key)) return null;
           return (
             <div key={key} style={{ display: 'flex', marginBottom: '12px', fontSize: '13px' }}>
               <div style={{ color: '#909296', width: '100px', flexShrink: 0, textTransform: 'capitalize' }}>
                 {key.replace(/([A-Z])/g, ' $1').trim()}
               </div>
               <div style={{ color: '#c1c2c5', wordBreak: 'break-all' }}>{value}</div>
             </div>
           );
        })}
        
        {/* Actions */}
        <div style={{ marginTop: '24px' }}>
            <button style={{ width: '100%', padding: '8px', background: '#2c2e33', border: '1px solid #373a40', color: '#c1c2c5', borderRadius: '3px', marginBottom: '8px', cursor: 'pointer', fontSize: '13px' }}>
              Edit Details
            </button>
            <button style={{ width: '100%', padding: '8px', background: 'rgba(255, 107, 107, 0.1)', border: '1px solid rgba(255, 107, 107, 0.2)', color: '#ff6b6b', borderRadius: '3px', cursor: 'pointer', fontSize: '13px' }}>
              Delete Item
            </button>
        </div>

      </div>
    </div>
  );
};

export default PreviewPanel;
