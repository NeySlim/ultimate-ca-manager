import React, { useState } from 'react';
import { useView } from '../../../core/context/ViewContext';
import CertificateListView from '../components/CertificateListView';
import CertificateGridView from '../components/CertificateGridView';

const MOCK_DATA = [
  { id: 1, name: 'api.example.com', modified: '2 days ago', algo: 'RSA 2048', expiresIn: '245 days', status: 'Valid', icon: 'cert' },
  { id: 2, name: 'web.app.com', modified: '5 days ago', algo: 'RSA 2048', expiresIn: '45 days', status: 'Warning', icon: 'cert' },
  { id: 3, name: 'mail.srv.com', modified: '1 week ago', algo: 'RSA 4096', expiresIn: '320 days', status: 'Valid', icon: 'cert' },
  { id: 4, name: 'vpn.gateway.lan', modified: '3 months ago', algo: 'EC P-256', expiresIn: '-5 days', status: 'Error', icon: 'lock' },
  { id: 5, name: 'ldap.corp.internal', modified: '2 weeks ago', algo: 'RSA 2048', expiresIn: '180 days', status: 'Valid', icon: 'cert' },
  { id: 6, name: 'db.prod.internal', modified: '1 month ago', algo: 'RSA 2048', expiresIn: '300 days', status: 'Valid', icon: 'cert' },
  { id: 7, name: 'monitoring.sys', modified: '1 day ago', algo: 'EC P-384', expiresIn: '90 days', status: 'Valid', icon: 'cert' },
];

const CertificatesPage = () => {
  const { viewMode } = useView();
  const [selectedId, setSelectedId] = useState(1);

  const handleSelect = (item) => {
    setSelectedId(item.id);
    // In future: setGlobalSelection(item); for PreviewPanel
  };

  const ViewComponent = viewMode === 'grid' ? CertificateGridView : CertificateListView;

  return (
    <ViewComponent 
      items={MOCK_DATA} 
      selectedId={selectedId} 
      onSelect={handleSelect} 
    />
  );
};

export default CertificatesPage;
