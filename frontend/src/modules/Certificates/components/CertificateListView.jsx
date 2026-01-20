import React from 'react';
import { Grid, Widget, PageHeader } from '../../../components/ui/Layout';
import CertificateTable from './CertificateTable';
import { Plus } from '@phosphor-icons/react';
import { Button } from '@mantine/core';

const CertificateListView = ({ items, onSelect, selectedId }) => {
  return (
    <div className="certificates-list-page" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* 1. Standard Page Header */}
      <PageHeader 
        title="Certificates" 
        actions={
          <Button leftSection={<Plus size={16} />} size="xs" variant="filled" color="blue">
            New Certificate
          </Button>
        }
      />

      {/* 2. Content (Standard Grid Layout) */}
      <div className="certificates-content" style={{ flex: 1 }}>
        <Grid>
           {/* Full Width Widget for Table */}
           <Widget className="widget-full" style={{ height: 'calc(100vh - 120px)' }}>
              <CertificateTable 
                 data={items} 
                 onRowClick={onSelect}
                 selectedId={selectedId}
              />
           </Widget>
        </Grid>
      </div>
    </div>
  );
};

export default CertificateListView;
