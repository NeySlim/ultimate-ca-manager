import React from 'react';
import { Export, ArrowsClockwise, Copy, Trash } from '@phosphor-icons/react';
import { useSelection } from '../../../core/context/SelectionContext';

const PreviewPanel = () => {
  const { selectedItem } = useSelection();

  if (!selectedItem) {
    return (
      <div className="preview-panel" style={{ alignItems: 'center', justifyContent: 'center', color: '#666' }}>
        <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '48px', marginBottom: '16px', opacity: 0.3 }}>👆</div>
            <p>Select an item to view details</p>
        </div>
      </div>
    );
  }

  return (
    <div className="preview-panel">
      <div className="preview-header">
        <div className="preview-icon">
            {selectedItem.icon === 'cert' ? '📜' : '🔒'}
        </div>
        <div className="preview-title">{selectedItem.name}</div>
        <div className="preview-subtitle">{selectedItem.algo || 'Unknown Type'}</div>
      </div>
      
      <div className="preview-content">
        <div className="preview-section">
          <div className="label">Common Name</div>
          <div className="value">{selectedItem.name}</div>
        </div>
        
        <div className="preview-section">
          <div className="label">Status</div>
          <div className="value">
             <span className={`status-badge ${selectedItem.status?.toLowerCase() || 'valid'}`}>
                {selectedItem.status || 'Active'}
             </span>
          </div>
        </div>

        {/* Dynamic Mock Data for demo purposes if not present in item */}
        <div className="preview-section">
          <div className="label">Serial Number</div>
          <div className="value"><code>{selectedItem.serial || 'A3:4F:2B:8E:91:CC:7D:45'}</code></div>
        </div>
        
        <div className="preview-section">
          <div className="label">Validity Period</div>
          <div className="value">
            <strong>Expires:</strong> {selectedItem.expiresIn}<br/>
          </div>
          <div className="progress-bar">
            <div className="progress-fill" style={{ width: '67%' }}></div>
          </div>
        </div>
      </div>
      
      <div className="preview-actions">
        <button className="primary" title="Export PEM"><Export /></button>
        <button className="secondary" title="Renew Certificate"><ArrowsClockwise /></button>
        <button className="secondary" title="Copy Details"><Copy /></button>
        <button className="danger" title="Delete Certificate"><Trash /></button>
      </div>
    </div>
  );
};

export default PreviewPanel;
