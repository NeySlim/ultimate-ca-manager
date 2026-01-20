import React from 'react';
import { Grid, Widget, PageHeader } from '../../../components/ui/Layout';
import { FileText, ShieldCheck, Plus } from '@phosphor-icons/react';
import { Button } from '../../../components/ui';

const CertificateGridView = ({ items, onSelect, selectedId }) => {
  return (
    <div className="certificates-grid-page" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* 1. Standard Page Header */}
      <PageHeader 
        title="Certificates" 
        actions={
          <Button leftSection={<Plus size={16} />} size="xs" variant="filled" color="blue">
            New Certificate
          </Button>
        }
      />

      {/* 2. Content (Grid Layout) */}
      <div className="certificates-content" style={{ flex: 1, overflow: 'auto', padding: 'var(--spacing-lg)' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 'var(--spacing-lg)' }}>
            {items.map(item => (
                <Widget 
                key={item.id}
                className={`${selectedId === item.id ? 'selected' : ''}`}
                style={{ 
                    cursor: 'pointer',
                    minHeight: '180px',
                    borderColor: selectedId === item.id ? 'var(--accent-primary)' : undefined
                }}
                onClick={() => onSelect(item)}
                >
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 'var(--spacing-md)', height: '100%' }}>
                        <div style={{ fontSize: 'var(--icon-size-xl)', color: 'var(--text-muted)' }}>
                            {item.icon === 'cert' ? <FileText weight="thin" /> : <ShieldCheck weight="thin" />}
                        </div>
                        <div style={{ textAlign: 'center', width: '100%' }}>
                            <div style={{ fontSize: 'var(--font-size-ui)', fontWeight: 600, color: 'var(--text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                {item.commonName || item.name}
                            </div>
                            <div style={{ fontSize: 'var(--font-size-label)', color: 'var(--text-tertiary)', marginTop: 'var(--spacing-xs)' }}>
                                {item.serial ? item.serial.substring(0, 10) + '...' : item.algo}
                            </div>
                        </div>
                        <div style={{ marginTop: 'auto' }}>
                            <span className={`status-badge ${item.status?.toLowerCase() || 'valid'}`} 
                                style={{ 
                                    padding: '2px var(--spacing-sm)', 
                                    borderRadius: 'var(--radius)', 
                                    fontSize: '10px', 
                                    fontWeight: 600,
                                    textTransform: 'uppercase',
                                    backgroundColor: item.status === 'Valid' ? 'rgba(129, 199, 132, 0.15)' : 'rgba(100, 100, 100, 0.2)',
                                    color: item.status === 'Valid' ? 'var(--status-success)' : 'var(--text-secondary)'
                                }}>
                                {item.status || 'Unknown'}
                            </span>
                        </div>
                    </div>
                </Widget>
            ))}
          </div>
      </div>
    </div>
  );
};

export default CertificateGridView;
