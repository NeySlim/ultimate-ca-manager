import React, { useState, useEffect } from 'react';
import {
  Button,
  Group,
  Text,
  Badge,
} from '@mantine/core';
import {
  DeviceMobile,
  Gear,
  CheckCircle,
  XCircle,
  Clock,
  ListDashes,
} from '@phosphor-icons/react';
import { PageHeader, Grid, Widget } from '../../../components/ui/Layout';
import StatWidget from '../../Dashboard/components/widgets/StatWidget';
import ResizableTable from '../../../components/ui/Layout/ResizableTable';
import { ScepService } from '../services/scep.service';
import './SCEPPage.css';

const SCEPPage = () => {
  const [stats, setStats] = useState({
    total: 0,
    pending: 0,
    approved: 0,
    rejected: 0
  });
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [statsData, requestsData] = await Promise.all([
        ScepService.getStats(),
        ScepService.getRequests()
      ]);
      setStats(statsData);
      setRequests(requestsData);
    } catch (error) {
      console.error("Failed to load SCEP data", error);
    } finally {
      setLoading(false);
    }
  };

  const columns = [
    {
      key: 'transactionId',
      label: 'Transaction ID',
      width: 250,
      render: (row) => (
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <DeviceMobile size={18} className="icon-gradient-subtle" style={{ marginRight: 8 }} />
          <Text size="xs" className="mono-text" truncate>{row.transaction_id || row.transactionId}</Text>
        </div>
      )
    },
    {
      key: 'subject',
      label: 'Subject (Device)',
      width: 200,
      render: (row) => <Text size="sm" fw={500}>{row.subject}</Text>
    },
    {
      key: 'status',
      label: 'Status',
      width: 100,
      render: (row) => (
        <Badge 
          color={row.status === 'approved' || row.status === 'Success' ? 'green' : row.status === 'rejected' || row.status === 'Failed' ? 'red' : 'blue'} 
          variant="dot"
          size="sm"
        >
          {row.status}
        </Badge>
      )
    },
    {
      key: 'created_at',
      label: 'Time',
      width: 150,
      render: (row) => <Text size="sm" c="dimmed">{new Date(row.created_at || row.timestamp).toLocaleString()}</Text>
    }
  ];

  return (
    <div className="scep-page" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <PageHeader 
        title="SCEP Protocol" 
        actions={
          <Button variant="light" leftSection={<Gear size={16} />} size="xs">
            Settings
          </Button>
        }
      />

      <Grid style={{ flex: 1, padding: '16px' }}>
        {/* Top Stats */}
        <div className="widget-1-3">
          <StatWidget
            icon={<DeviceMobile size={32} weight="duotone" className="icon-gradient-glow" />}
            value={stats.approved}
            label="Enrolled Devices"
            color="blue"
          />
        </div>
        <div className="widget-1-3">
          <StatWidget
            icon={<CheckCircle size={32} weight="duotone" className="icon-gradient-glow" />}
            value={stats.pending}
            label="Pending Requests"
            color="green"
          />
        </div>
        <div className="widget-1-3">
          <StatWidget
            icon={<XCircle size={32} weight="duotone" className="icon-gradient-glow" />}
            value={stats.rejected}
            label="Failures / Rejected"
            color="red"
          />
        </div>

        {/* Requests Table */}
        <Widget 
          title="Recent Requests" 
          icon={<ListDashes size={20} className="icon-gradient-subtle" />} 
          className="widget-full" 
          style={{ flex: 1, padding: 0, overflow: 'hidden' }}
        >
          <ResizableTable 
            columns={columns}
            data={requests}
            onRowClick={(row) => console.log('Clicked request', row)}
            emptyMessage="No SCEP requests found"
          />
        </Widget>
      </Grid>
    </div>
  );
};

export default SCEPPage;
