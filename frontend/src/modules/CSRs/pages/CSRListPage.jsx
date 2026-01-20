import React, { useState } from 'react';
import {
  Button,
  Group,
  Badge,
  Text,
  ActionIcon,
  Tooltip,
} from '@mantine/core';
import {
  Plus,
  FileText,
  PenNib,
  Eye,
  Trash,
  CheckCircle,
} from '@phosphor-icons/react';
import { PageHeader, Grid, Widget } from '../../../components/ui/Layout';
import ResizableTable from '../../../components/ui/Layout/ResizableTable';
import './CSRListPage.css';

// Mock Data
const MOCK_CSRS = [
  {
    id: 1,
    commonName: 'web.internal.corp',
    org: 'MyCorp Internal',
    algo: 'RSA 2048',
    status: 'Pending',
    created: '2024-03-15T10:30:00Z',
    requester: 'admin'
  },
  {
    id: 2,
    commonName: 'vpn.gateway.net',
    org: 'NetOps Division',
    algo: 'ECDSA P-256',
    status: 'Pending',
    created: '2024-03-14T15:45:00Z',
    requester: 'operator'
  },
  {
    id: 3,
    commonName: 'legacy-app.local',
    org: 'Legacy Systems',
    algo: 'RSA 4096',
    status: 'Signed',
    created: '2024-03-10T09:00:00Z',
    requester: 'admin'
  }
];

const CSRListPage = () => {
  const [data, setData] = useState(MOCK_CSRS);

  const columns = [
    {
      key: 'commonName',
      label: 'Common Name',
      width: 250,
      minWidth: 150,
      render: (row) => (
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <FileText size={18} className="icon-gradient-subtle" style={{ marginRight: 8 }} />
          <Text size="sm" fw={500}>{row.commonName}</Text>
        </div>
      )
    },
    {
      key: 'org',
      label: 'Organization',
      width: 180,
      render: (row) => <Text size="sm">{row.org}</Text>
    },
    {
      key: 'algo',
      label: 'Algorithm',
      width: 120,
      render: (row) => <Badge variant="outline" color="gray" size="xs">{row.algo}</Badge>
    },
    {
      key: 'status',
      label: 'Status',
      width: 100,
      render: (row) => (
        <Badge 
          color={row.status === 'Signed' ? 'green' : 'blue'} 
          variant="dot" 
          size="sm"
        >
          {row.status}
        </Badge>
      )
    },
    {
      key: 'requester',
      label: 'Requester',
      width: 120,
      render: (row) => <Text size="sm" c="dimmed">{row.requester}</Text>
    },
    {
      key: 'created',
      label: 'Created',
      width: 150,
      render: (row) => <Text size="sm" c="dimmed">{new Date(row.created).toLocaleDateString()}</Text>
    },
    {
      key: 'actions',
      label: 'Actions',
      width: 140,
      render: (row) => (
        <Group gap={4}>
          <Tooltip label="View Details">
            <ActionIcon size="sm" variant="light">
              <Eye size={16} />
            </ActionIcon>
          </Tooltip>
          {row.status === 'Pending' && (
            <Tooltip label="Sign Request">
              <ActionIcon size="sm" variant="filled" color="blue">
                <PenNib size={16} />
              </ActionIcon>
            </Tooltip>
          )}
          <Tooltip label="Delete">
            <ActionIcon size="sm" variant="light" color="red">
              <Trash size={16} />
            </ActionIcon>
          </Tooltip>
        </Group>
      )
    }
  ];

  return (
    <div className="csr-list-page" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <PageHeader 
        title="Certificate Signing Requests" 
        actions={
          <Button leftSection={<Plus size={16} />} size="xs">
            New CSR
          </Button>
        }
      />

      <Grid style={{ flex: 1, padding: '16px' }}>
        <Widget className="widget-full" style={{ height: '100%', padding: 0, overflow: 'hidden' }}>
          <ResizableTable 
            columns={columns}
            data={data}
            onRowClick={(row) => console.log('Clicked CSR', row)}
            emptyMessage="No Pending CSRs"
          />
        </Widget>
      </Grid>
    </div>
  );
};

export default CSRListPage;
