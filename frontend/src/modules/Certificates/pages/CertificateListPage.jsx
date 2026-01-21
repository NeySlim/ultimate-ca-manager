import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Certificate, Plus } from '@phosphor-icons/react';
import { Button, Stack, Card, Text, Loader, StatusBadge, SearchToolbar, Select } from '../../../components/ui';
import { certificateService } from '../services/certificate.service';
import '../../../styles/common-page.css';

const CertificateListPage = () => {
  const [certs, setCerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const navigate = useNavigate();

  useEffect(() => {
    loadCertificates();
  }, [statusFilter]);

  const loadCertificates = async () => {
    try {
      setLoading(true);
      const params = statusFilter !== 'all' ? { status: statusFilter } : {};
      const data = await certificateService.getAll(params);
      setCerts(data.certificates || []);
    } catch (error) {
      console.error('Failed to load certificates:', error);
    } finally {
      setLoading(false);
    }
  };

  const filteredCerts = certs.filter(cert =>
    cert.descr?.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="page-container">
      <div className="page-header">
        <div className="page-header-left">
          <Certificate size={28} weight="duotone" className="icon-gradient" />
          <div>
            <h1 className="page-title">Certificates</h1>
            <Text className="page-subtitle">{certs.length} certificate(s) total</Text>
          </div>
        </div>
        <Button variant="primary" onClick={() => navigate('/certificates/create')}>
          <Plus size={16} weight="bold" />
          Issue Certificate
        </Button>
      </div>

      <SearchToolbar
        placeholder="Search certificates..."
        value={search}
        onChange={setSearch}
        filters={[
          <Select
            value={statusFilter}
            onChange={setStatusFilter}
            data={[
              { value: 'all', label: 'All Status' },
              { value: 'valid', label: 'Valid' },
              { value: 'expired', label: 'Expired' },
              { value: 'revoked', label: 'Revoked' }
            ]}
            size="sm"
          />
        ]}
      />

      {loading ? (
        <div className="loading-center"><Loader /></div>
      ) : filteredCerts.length === 0 ? (
        <Card className="empty-state-card">
          <Certificate size={48} weight="thin" className="empty-icon" />
          <Text className="empty-text">No certificates found</Text>
          <Button variant="primary" onClick={() => navigate('/certificates/create')}>Issue First Certificate</Button>
        </Card>
      ) : (
        <Stack>
          {filteredCerts.map(cert => (
            <Card key={cert.refid} className="list-item-card" onClick={() => navigate(`/certificates/${cert.refid}`)}>
              <div className="list-item-content">
                <div className="list-item-icon">
                  <Certificate size={32} weight="duotone" className="icon-gradient" />
                </div>
                <div className="list-item-details">
                  <Text className="list-item-title">{cert.descr || cert.cn}</Text>
                  <Text className="list-item-subtitle">Expires {cert.validto_time}</Text>
                </div>
                <div className="list-item-badges">
                  <StatusBadge status={cert.status} context="certificate" />
                </div>
              </div>
            </Card>
          ))}
        </Stack>
      )}
    </div>
  );
};

export default CertificateListPage;
