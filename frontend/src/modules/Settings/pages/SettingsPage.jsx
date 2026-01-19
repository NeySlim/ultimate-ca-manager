import React from 'react';
import { useModals } from '@mantine/modals';
import { Gear, Globe, ShieldCheck, Database, Cloud } from '@phosphor-icons/react';
import AcmeConfigModal from '../components/AcmeConfigModal';
import ScepConfigModal from '../components/ScepConfigModal';

const SettingsPage = () => {
  const modals = useModals();

  const openAcmeModal = () => {
    modals.openModal({
      title: 'ACME Protocol Configuration',
      centered: true,
      children: <AcmeConfigModal />,
    });
  };

  const openScepModal = () => {
    modals.openModal({
      title: 'SCEP Protocol Configuration',
      centered: true,
      children: <ScepConfigModal />,
    });
  };

  const configs = [
    { id: 'acme', name: 'ACME Provider', type: 'Protocol', icon: Globe, action: openAcmeModal, status: 'Active' },
    { id: 'scep', name: 'SCEP Server', type: 'Protocol', icon: ShieldCheck, action: openScepModal, status: 'Idle' },
    { id: 'db', name: 'Database Connection', type: 'System', icon: Database, action: () => {}, status: 'Connected' },
    { id: 'backup', name: 'Cloud Backup', type: 'Storage', icon: Cloud, action: () => {}, status: 'Daily' },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div className="list-header">
        <div>Configuration Name</div>
        <div>Category</div>
        <div>Last Modified</div>
        <div>Status</div>
        <div>Action</div>
      </div>
      
      <div className="file-list">
        {configs.map(item => (
          <div key={item.id} className="file-item" onClick={item.action}>
            <div className="file-name">
              <span className="icon"><item.icon /></span>
              <span>{item.name}</span>
            </div>
            <div className="file-type">{item.type}</div>
            <div className="file-meta">Today</div>
            <div>
              <span className={`status-badge ${item.status === 'Active' || item.status === 'Connected' ? 'valid' : 'warning'}`}>
                {item.status}
              </span>
            </div>
            <div className="file-meta" style={{textAlign: 'right'}}>
                <Gear />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default SettingsPage;
