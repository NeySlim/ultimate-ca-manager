import React from 'react';
import { FileText, ShieldCheck } from '@phosphor-icons/react';

const CertificateGridView = ({ items, onSelect, selectedId }) => {
  return (
    <div className="file-list" style={{ display: 'flex', flexWrap: 'wrap', gap: '16px', padding: '16px', alignContent: 'flex-start' }}>
      {items.map(item => (
        <div 
          key={item.id}
          className={`file-item ${selectedId === item.id ? 'selected' : ''}`}
          onClick={() => onSelect(item)}
          style={{ 
            display: 'flex', 
            flexDirection: 'column', 
            width: '140px', 
            height: '160px', 
            alignItems: 'center', 
            justifyContent: 'flex-start',
            textAlign: 'center',
            padding: '16px',
            gridTemplateColumns: 'none', // Override list grid
            gap: '8px'
          }}
        >
          <div style={{ fontSize: '48px', color: '#666', marginBottom: '4px' }}>
             {item.icon === 'cert' ? <FileText weight="thin" /> : <ShieldCheck weight="thin" />}
          </div>
          <div style={{ fontSize: '13px', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', width: '100%', whiteSpace: 'nowrap' }}>
            {item.name}
          </div>
          <div style={{ fontSize: '11px', color: '#666' }}>{item.algo}</div>
          
          <div className={`status-badge ${item.status.toLowerCase()}`} style={{ marginTop: 'auto', fontSize: '10px', padding: '2px 8px' }}>
            {item.status}
          </div>
        </div>
      ))}
    </div>
  );
};

export default CertificateGridView;
