import React from 'react';
import { Export, ArrowsClockwise, Copy, Trash } from '@phosphor-icons/react';

const PreviewPanel = () => {
  // Static placeholder for now, matching the design mock
  return (
    <div className="preview-panel">
      <div className="preview-header">
        <div className="preview-icon">📜</div>
        <div className="preview-title">api.example.com</div>
        <div className="preview-subtitle">RSA 2048-bit Certificate</div>
      </div>
      
      <div className="preview-content">
        <div className="preview-section">
          <div className="label">Common Name</div>
          <div className="value">api.example.com</div>
        </div>
        
        <div className="preview-section">
          <div className="label">Organization</div>
          <div className="value">Acme Inc, Engineering Department</div>
        </div>
        
        <div className="preview-section">
          <div className="label">Serial Number</div>
          <div className="value"><code>A3:4F:2B:8E:91:CC:7D:45</code></div>
        </div>
        
        <div className="preview-section">
          <div className="label">Issuer</div>
          <div className="value">CN=Internal Intermediate CA<br/>O=Acme Inc<br/>C=US</div>
        </div>
        
        <div className="preview-section">
          <div className="label">Validity Period</div>
          <div className="value">
            <strong>From:</strong> Jan 15, 2024 00:00 UTC<br/>
            <strong>To:</strong> Dec 31, 2025 23:59 UTC
          </div>
          <div className="progress-bar">
            <div className="progress-fill" style={{ width: '67%' }}></div>
          </div>
          <div className="value" style={{ marginTop: '4px', fontSize: '11px', color: '#4a9eff' }}>
            245 days remaining (67%)
          </div>
        </div>
        
        <div className="preview-section">
          <div className="label">Subject Alternative Names</div>
          <div className="value">
            • DNS: api.example.com<br/>
            • DNS: *.api.example.com<br/>
            • DNS: staging-api.example.com
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
