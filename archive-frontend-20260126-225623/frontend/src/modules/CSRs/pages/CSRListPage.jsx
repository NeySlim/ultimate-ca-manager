import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { FileText, Plus } from '@phosphor-icons/react';
import { Button, Stack, Card, Text, Loader, SearchToolbar } from '../../../components/ui';
import { csrService } from '../services/csr.service';
import '../../../styles/common-page.css';

const CSRListPage = () => {
  const [csrs, setCsrs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    loadCSRs();
  }, []);

  const loadCSRs = async () => {
    try {
      setLoading(true);
      const data = await csrService.getAll();
      setCsrs(data.csrs || []);
    } catch (error) {
      console.error('Failed to load CSRs:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page-container">
      <div className="page-header">
        <div className="page-header-left">
          <FileText size={28} weight="duotone" className="icon-gradient" />
          <div>
            <h1 className="page-title">Certificate Requests</h1>
            <Text className="page-subtitle">{csrs.length} CSR(s) total</Text>
          </div>
        </div>
        <Button variant="primary" onClick={() => navigate('/csrs/create')}>
          <Plus size={16} weight="bold" />
          Create CSR
        </Button>
      </div>

      <SearchToolbar
        placeholder="Search certificate requests..."
        value={search}
        onChange={setSearch}
      />

      {loading ? (
        <div className="loading-center"><Loader /></div>
      ) : csrs.length === 0 ? (
        <Card className="empty-state-card">
          <FileText size={48} weight="thin" className="empty-icon" />
          <Text className="empty-text">No certificate requests found</Text>
          <Button variant="primary" onClick={() => navigate('/csrs/create')}>Create First CSR</Button>
        </Card>
      ) : (
        <Stack>
          {csrs.map(csr => (
            <Card key={csr.refid} className="list-item-card" onClick={() => navigate(`/csrs/${csr.refid}`)}>
              <div className="list-item-content">
                <div className="list-item-icon">
                  <FileText size={32} weight="duotone" className="icon-gradient" />
                </div>
                <div className="list-item-details">
                  <Text className="list-item-title">{csr.descr || csr.cn}</Text>
                  <Text className="list-item-subtitle">Created {csr.created_at}</Text>
                </div>
              </div>
            </Card>
          ))}
        </Stack>
      )}
    </div>
  );
};

export default CSRListPage;
