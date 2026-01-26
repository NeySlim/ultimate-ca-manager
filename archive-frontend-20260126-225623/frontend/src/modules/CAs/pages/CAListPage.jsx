import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ShieldCheck, Plus, MagnifyingGlass } from '@phosphor-icons/react';
import { Button, Stack, Card, Text, Loader, StatusBadge, SearchToolbar } from '../../../components/ui';
import { caService } from '../services/ca.service';
import '../../../styles/common-page.css';

const CAListPage = () => {
  const [cas, setCas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    loadCAs();
  }, []);

  const loadCAs = async () => {
    try {
      setLoading(true);
      const data = await caService.getAll();
      setCas(data.cas || []);
    } catch (error) {
      console.error('Failed to load CAs:', error);
    } finally {
      setLoading(false);
    }
  };

  const filteredCAs = cas.filter(ca =>
    ca.descr?.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="page-container">
      <div className="page-header">
        <div className="page-header-left">
          <ShieldCheck size={28} weight="duotone" className="icon-gradient" />
          <div>
            <h1 className="page-title">Certificate Authorities</h1>
            <Text className="page-subtitle">{cas.length} CA(s) total</Text>
          </div>
        </div>
        <Button variant="primary" onClick={() => navigate('/cas/create')}>
          <Plus size={16} weight="bold" />
          Create CA
        </Button>
      </div>

      <SearchToolbar
        placeholder="Search certificate authorities..."
        value={search}
        onChange={setSearch}
      />

      {loading ? (
        <div className="loading-center"><Loader /></div>
      ) : filteredCAs.length === 0 ? (
        <Card className="empty-state-card">
          <ShieldCheck size={48} weight="thin" className="empty-icon" />
          <Text className="empty-text">No certificate authorities found</Text>
          <Button variant="primary" onClick={() => navigate('/cas/create')}>Create First CA</Button>
        </Card>
      ) : (
        <Stack>
          {filteredCAs.map(ca => (
            <Card key={ca.refid} className="list-item-card" onClick={() => navigate(`/cas/${ca.refid}`)}>
              <div className="list-item-content">
                <div className="list-item-icon">
                  <ShieldCheck size={32} weight="duotone" className="icon-gradient" />
                </div>
                <div className="list-item-details">
                  <Text className="list-item-title">{ca.descr}</Text>
                  <Text className="list-item-subtitle">Created {ca.created_at}</Text>
                </div>
                <div className="list-item-badges">
                  <StatusBadge status={ca.catype} context="ca" />
                  <StatusBadge status="active" context="ca" />
                </div>
              </div>
            </Card>
          ))}
        </Stack>
      )}
    </div>
  );
};

export default CAListPage;
