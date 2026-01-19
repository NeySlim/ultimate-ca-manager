import React from 'react';
import { useView } from '../../../core/context/ViewContext';
import CertificateGridView from '../../Certificates/components/CertificateGridView';
import { Clock, Star } from '@phosphor-icons/react';

const RECENT_FILES = [
  { id: 1, name: 'api.example.com', modified: '2 hours ago', algo: 'RSA 2048', expiresIn: '245 days', status: 'Valid', icon: 'cert' },
  { id: 4, name: 'vpn.gateway.lan', modified: 'Yesterday', algo: 'EC P-256', expiresIn: '-5 days', status: 'Error', icon: 'lock' },
  { id: 2, name: 'web.app.com', modified: '5 days ago', algo: 'RSA 2048', expiresIn: '45 days', status: 'Warning', icon: 'cert' },
];

const DashboardPage = () => {
  return (
    <div style={{ padding: '20px', overflowY: 'auto', height: '100%' }}>
      
      {/* Quick Access / Stats Section */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px', marginBottom: '32px' }}>
        <div style={{ background: '#242424', padding: '20px', borderRadius: '8px', border: '1px solid #333' }}>
            <div style={{ color: '#888', fontSize: '12px', textTransform: 'uppercase', marginBottom: '8px' }}>Total Certificates</div>
            <div style={{ fontSize: '32px', fontWeight: 'bold', color: '#e8e8e8' }}>1,248</div>
            <div style={{ color: '#4a9eff', fontSize: '12px', marginTop: '4px' }}>+12 this week</div>
        </div>
        <div style={{ background: '#242424', padding: '20px', borderRadius: '8px', border: '1px solid #333' }}>
            <div style={{ color: '#888', fontSize: '12px', textTransform: 'uppercase', marginBottom: '8px' }}>Expiring Soon</div>
            <div style={{ fontSize: '32px', fontWeight: 'bold', color: '#ffb74d' }}>5</div>
            <div style={{ color: '#666', fontSize: '12px', marginTop: '4px' }}>Action required</div>
        </div>
        <div style={{ background: '#242424', padding: '20px', borderRadius: '8px', border: '1px solid #333' }}>
            <div style={{ color: '#888', fontSize: '12px', textTransform: 'uppercase', marginBottom: '8px' }}>Revoked</div>
            <div style={{ fontSize: '32px', fontWeight: 'bold', color: '#e57373' }}>2</div>
            <div style={{ color: '#666', fontSize: '12px', marginTop: '4px' }}>In the last 30 days</div>
        </div>
      </div>

      {/* Recent Files Section */}
      <div style={{ marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px', color: '#ccc' }}>
        <Clock weight="bold" />
        <h3 style={{ fontSize: '14px', fontWeight: 600 }}>Recent Files</h3>
      </div>
      
      {/* Reusing Grid View for Recents */}
      <div style={{ background: '#1e1e1e', borderRadius: '8px', border: '1px solid #333' }}>
        <CertificateGridView items={RECENT_FILES} selectedId={null} onSelect={() => {}} />
      </div>

    </div>
  );
};

export default DashboardPage;
