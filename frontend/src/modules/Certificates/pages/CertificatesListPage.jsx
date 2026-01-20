import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader, Center, Button } from '@mantine/core';
import { Plus, Upload } from '@phosphor-icons/react';
import { Grid, Widget, PageHeader } from '../../../components/ui/Layout';
import CertificateTable from '../components/CertificateTable';
import { CertificateService } from '../services/certificates.service';
import './CertificatesListPage.css';

const CertificatesListPage = () => {
  const navigate = useNavigate();
  const [certificates, setCertificates] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadCertificates();
  }, []);

  const loadCertificates = async () => {
    try {
      setLoading(true);
      const data = await CertificateService.getAll();
      setCertificates(data);
    } catch (error) {
      console.error('Failed to load certificates', error);
    } finally {
      setLoading(false);
    }
  };

  const handleRowClick = (certificate) => {
    navigate(`/certificates/${certificate.id}`);
  };

  const handleViewDetails = (certificate) => {
    navigate(`/certificates/${certificate.id}`);
  };

  const handleDownload = (certificate) => {
    const element = document.createElement('a');
    element.setAttribute('href', 'data:text/plain;charset=utf-8,' + encodeURIComponent(certificate.pem));
    element.setAttribute('download', `${certificate.commonName}.pem`);
    element.style.display = 'none';
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
  };

  const handleDelete = (certificate) => {
    if (window.confirm(`Are you sure you want to delete ${certificate.commonName}?`)) {
      console.log('Deleting certificate:', certificate.id);
      setCertificates(certificates.filter(cert => cert.id !== certificate.id));
    }
  };

  if (loading) {
    return (
      <Center style={{ height: '100vh' }}>
        <Loader color="blue" type="bars" />
      </Center>
    );
  }

  return (
    <div className="certificates-list-page" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* 1. Page Header (Sticky) */}
      <PageHeader
        title="Certificates"
        actions={
          <div style={{ display: 'flex', gap: '8px' }}>
            <Button
              leftSection={<Upload size={16} />}
              variant="default"
              size="xs"
              onClick={() => console.log('Import certificate')}
            >
              Import
            </Button>
            <Button
              leftSection={<Plus size={16} />}
              size="xs"
              onClick={() => console.log('Create new certificate')}
            >
              Create
            </Button>
          </div>
        }
      />

      {/* 2. Content (Standard Grid Layout) */}
      <Grid style={{ flex: 1, padding: '16px' }}>
         {/* Full Width Widget for Table */}
         <Widget className="widget-full" style={{ height: '100%', padding: 0, overflow: 'hidden' }}>
            <CertificateTable
              data={certificates}
              onRowClick={handleRowClick}
              onView={handleViewDetails}
              onDownload={handleDownload}
              onDelete={handleDelete}
            />
         </Widget>
      </Grid>
    </div>
  );
};

export default CertificatesListPage;
