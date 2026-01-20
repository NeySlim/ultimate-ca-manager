import React from 'react';
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
import './SCEPPage.css';

// Mock Data
const MOCK_SCEP_STATS = {
  activeDevices: 342,
  requestsToday: 12,
  failures: 0
};

const MOCK_REQUESTS = [
  {
    id: 1,
    transactionId: '123e4567-e89b-12d3-a456-426614174000',
    subject: 'iPad-Finance-001',
    status: 'Success',
    timestamp: '2024-03-20T10:30:00Z',
    type: 'PKCSReq'
  },
  {
    id: 2,
    transactionId: '987fcdeb-51a2-43c1-z987-123456789012',
    subject: 'MacBook-Dev-042',
    status: 'Pending',
    timestamp: '2024-03-20T10:15:00Z',
    type: 'GetCACaps'
  },
  {
    id: 3,
    transactionId: '456a789b-cdef-0123-4567-890123456789',
    subject: 'iPhone-Sales-105',
    status: 'Failed',
    timestamp: '2024-03-19T16:45:00Z',
    type: 'PKCSReq'
  }
];

const SCEPPage = () => {
  const columns = [
    {
      key: 'transactionId',
      label: 'Transaction ID',
      width: 250,
      render: (row) => (
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <DeviceMobile size={18} className="icon-gradient-subtle" style={{ marginRight: 8 }} />
          <Text size="xs" className="mono-text" truncate>{row.transactionId}</Text>
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
      key: 'type',
      label: 'Operation',
      width: 120,
      render: (row) => <Badge variant="outline" color="gray" size="xs">{row.type}</Badge>
    },
    {
      key: 'status',
      label: 'Status',
      width: 100,
      render: (row) => (
        <Badge 
          color={row.status === 'Success' ? 'green' : row.status === 'Failed' ? 'red' : 'blue'} 
          variant="dot"
          size="sm"
        >
          {row.status}
        </Badge>
      )
    },
    {
      key: 'timestamp',
      label: 'Time',
      width: 150,
      render: (row) => <Text size="sm" c="dimmed">{new Date(row.timestamp).toLocaleString()}</Text>
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
            value={MOCK_SCEP_STATS.activeDevices}
            label="Enrolled Devices"
            color="blue"
          />
        </div>
        <div className="widget-1-3">
          <StatWidget
            icon={<CheckCircle size={32} weight="duotone" className="icon-gradient-glow" />}
            value={MOCK_SCEP_STATS.requestsToday}
            label="Requests (24h)"
            trend={{ value: 10, isPositive: true }}
            color="green"
          />
        </div>
        <div className="widget-1-3">
          <StatWidget
            icon={<XCircle size={32} weight="duotone" className="icon-gradient-glow" />}
            value={MOCK_SCEP_STATS.failures}
            label="Failures"
            trend={{ value: 0, isPositive: true }}
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
            data={MOCK_REQUESTS}
            onRowClick={(row) => console.log('Clicked request', row)}
          />
        </Widget>
      </Grid>
    </div>
  );
};

export default SCEPPage;
