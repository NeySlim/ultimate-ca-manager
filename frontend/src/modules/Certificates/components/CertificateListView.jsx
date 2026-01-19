import React from 'react';
import { FileText, LockKey, ShieldCheck } from '@phosphor-icons/react';

const CertificateListView = ({ items, onSelect, selectedId }) => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div className="list-header">
        <div>Name</div>
        <div>Modified</div>
        <div>Type</div>
        <div>Expires In</div>
        <div>Status</div>
      </div>
      
      <div className="file-list">
        {items.map(item => (
          <div 
            key={item.id} 
            className={`file-item ${selectedId === item.id ? 'selected' : ''}`}
            onClick={() => onSelect(item)}
          >
            <div className="file-name">
              <span className="icon">
                {item.icon === 'cert' ? <FileText /> : <ShieldCheck />}
              </span>
              <span>{item.name}</span>
            </div>
            <div className="file-meta">{item.modified}</div>
            <div className="file-type">{item.algo}</div>
            <div className="file-meta">{item.expiresIn}</div>
            <div>
              <span className={`status-badge ${item.status.toLowerCase()}`}>
                {item.status}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default CertificateListView;
