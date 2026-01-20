import React, { useState } from 'react';
import {
  Button,
  Group,
  Input,
  Select,
  Text,
  Badge,
  ActionIcon,
  Tooltip,
} from '@mantine/core';
import {
  MagnifyingGlass,
  Funnel,
  DownloadSimple,
  ClockCounterClockwise,
  CheckCircle,
  XCircle,
  Warning,
  User,
} from '@phosphor-icons/react';
import { PageHeader, Grid, Widget } from '../../../components/ui/Layout';
import ResizableTable from '../../../components/ui/Layout/ResizableTable';
import './AuditPage.css';

// Mock Data
const MOCK_LOGS = [
  { id: 1, timestamp: '2024-03-20T10:30:00Z', actor: 'admin', ip: '192.168.1.50', action: 'LOGIN_SUCCESS', resource: 'Auth', status: 'Success', details: 'Method: Password' },
  { id: 2, timestamp: '2024-03-20T10:35:00Z', actor: 'admin', ip: '192.168.1.50', action: 'CERT_ISSUE', resource: 'web.internal.corp', status: 'Success', details: 'Template: Web Server' },
  { id: 3, timestamp: '2024-03-20T11:00:00Z', actor: 'system', ip: 'localhost', action: 'CRL_GENERATE', resource: 'Root CA G1', status: 'Success', details: 'Items: 12' },
  { id: 4, timestamp: '2024-03-19T14:20:00Z', actor: 'operator', ip: '10.0.0.52', action: 'CERT_REVOKE', resource: 'old.internal.corp', status: 'Success', details: 'Reason: KeyCompromise' },
  { id: 5, timestamp: '2024-03-19T09:15:00Z', actor: 'unknown', ip: '192.168.1.200', action: 'LOGIN_FAILED', resource: 'Auth', status: 'Failure', details: 'Invalid Password' },
];

const AuditPage = () => {
  const [searchTerm, setSearchTerm] = useState('');

  const columns = [
    {
      key: 'timestamp',
      label: 'Timestamp',
      width: 180,
      render: (row) => <Text size="sm" className="mono-text">{new Date(row.timestamp).toLocaleString()}</Text>
    },
    {
      key: 'actor',
      label: 'Actor',
      width: 150,
      render: (row) => (
        <Group gap={6}>
            <User size={14} className="icon-gradient-subtle" />
            <Text size="sm" fw={500}>{row.actor}</Text>
        </Group>
      )
    },
    {
      key: 'ip',
      label: 'Source IP',
      width: 140,
      render: (row) => <Text size="sm" c="dimmed">{row.ip}</Text>
    },
    {
        key: 'action',
        label: 'Event Type',
        width: 180,
        render: (row) => <Badge variant="outline" size="sm">{row.action}</Badge>
    },
    {
        key: 'resource',
        label: 'Resource',
        width: 200,
        render: (row) => <Text size="sm">{row.resource}</Text>
    },
    {
        key: 'status',
        label: 'Status',
        width: 120,
        render: (row) => {
            const color = row.status === 'Success' ? 'green' : row.status === 'Failure' ? 'red' : 'orange';
            const Icon = row.status === 'Success' ? CheckCircle : row.status === 'Failure' ? XCircle : Warning;
            return (
                <Badge color={color} variant="dot" size="sm" style={{ paddingLeft: 0 }}>
                    <Group gap={4} ml={6}>
                        {row.status}
                    </Group>
                </Badge>
            );
        }
    },
    {
        key: 'details',
        label: 'Details',
        width: 250,
        render: (row) => <Text size="sm" c="dimmed" truncate>{row.details}</Text>
    }
  ];

  return (
    <div className="audit-page" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <PageHeader 
        title="Audit Logs" 
        actions={
          <Button variant="light" leftSection={<DownloadSimple size={16} />} size="xs">
            Export CSV
          </Button>
        }
      />

      <Grid style={{ flex: 1, padding: '16px', gridTemplateRows: 'auto 1fr' }}>
        {/* Filters */}
        <Widget className="col-12">
            <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                <Input 
                    placeholder="Search logs..." 
                    leftSection={<MagnifyingGlass size={16} />} 
                    style={{ flex: 1, maxWidth: '400px' }}
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                />
                <Select 
                    placeholder="Event Type" 
                    data={['LOGIN', 'CERT_ISSUE', 'CERT_REVOKE', 'SYSTEM']}
                    style={{ width: '180px' }}
                />
                <Select 
                    placeholder="Status" 
                    data={['Success', 'Failure', 'Warning']}
                    style={{ width: '150px' }}
                />
                <Button variant="default" leftSection={<Funnel size={16} />}>
                    More Filters
                </Button>
                <div style={{ flex: 1 }} />
                <Text size="sm" c="dimmed">Showing {MOCK_LOGS.length} events</Text>
            </div>
        </Widget>

        {/* Table */}
        <Widget className="col-12" style={{ padding: 0, overflow: 'hidden', minHeight: 0 }}>
          <ResizableTable 
            columns={columns}
            data={MOCK_LOGS}
            onRowClick={(row) => console.log('Clicked log', row)}
          />
        </Widget>
      </Grid>
    </div>
  );
};

export default AuditPage;
