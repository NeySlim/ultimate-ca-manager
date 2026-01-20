import React from 'react';
import {
  Button,
  Group,
  Text,
  Badge,
} from '@mantine/core';
import {
  Globe,
  Gear,
  CheckCircle,
  XCircle,
  ChartLineUp,
  ListDashes,
} from '@phosphor-icons/react';
import { PageHeader, Grid, Widget } from '../../../components/ui/Layout';
import StatWidget from '../../Dashboard/components/widgets/StatWidget';
import ResizableTable from '../../../components/ui/Layout/ResizableTable';
import './ACMEPage.css';

// Mock Data
const MOCK_ACME_STATS = {
  activeAccounts: 124,
  ordersToday: 45,
  errors: 2
};

const MOCK_ORDERS = [
  {
    id: 1,
    domain: 'api.service.io',
    account: 'provider-k8s-cluster',
    status: 'Valid',
    expires: '2024-06-15',
    method: 'DNS-01'
  },
  {
    id: 2,
    domain: 'auth.internal.net',
    account: 'legacy-server',
    status: 'Pending',
    expires: '2024-06-14',
    method: 'HTTP-01'
  },
  {
    id: 3,
    domain: 'test.dev.local',
    account: 'dev-team',
    status: 'Invalid',
    expires: '2024-06-10',
    method: 'DNS-01'
  }
];

const ACMEPage = () => {
  const columns = [
    {
      key: 'domain',
      label: 'Domain / Identifier',
      width: 250,
      render: (row) => (
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <Globe size={18} className="icon-gradient-subtle" style={{ marginRight: 8 }} />
          <Text size="sm" fw={500}>{row.domain}</Text>
        </div>
      )
    },
    {
      key: 'account',
      label: 'ACME Account',
      width: 200,
      render: (row) => <Text size="sm" c="dimmed">{row.account}</Text>
    },
    {
      key: 'method',
      label: 'Challenge',
      width: 100,
      render: (row) => <Badge variant="outline" color="gray" size="xs">{row.method}</Badge>
    },
    {
      key: 'status',
      label: 'Status',
      width: 100,
      render: (row) => (
        <Badge 
          color={row.status === 'Valid' ? 'green' : row.status === 'Invalid' ? 'red' : 'yellow'} 
          variant="dot"
          size="sm"
        >
          {row.status}
        </Badge>
      )
    },
    {
      key: 'expires',
      label: 'Expires',
      width: 120,
      render: (row) => <Text size="sm">{row.expires}</Text>
    }
  ];

  return (
    <div className="acme-page" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <PageHeader 
        title="ACME Protocol" 
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
            icon={<Globe size={32} weight="duotone" className="icon-gradient-glow" />}
            value={MOCK_ACME_STATS.activeAccounts}
            label="Active Accounts"
            color="blue"
          />
        </div>
        <div className="widget-1-3">
          <StatWidget
            icon={<CheckCircle size={32} weight="duotone" className="icon-gradient-glow" />}
            value={MOCK_ACME_STATS.ordersToday}
            label="Orders (24h)"
            trend={{ value: 5, isPositive: true }}
            color="green"
          />
        </div>
        <div className="widget-1-3">
          <StatWidget
            icon={<XCircle size={32} weight="duotone" className="icon-gradient-glow" />}
            value={MOCK_ACME_STATS.errors}
            label="Failed Challenges"
            trend={{ value: 1, isPositive: false }}
            color="red"
          />
        </div>

        {/* Orders Table */}
        <Widget 
          title="Recent Orders" 
          icon={<ListDashes size={20} className="icon-gradient-subtle" />} 
          className="widget-full" 
          style={{ flex: 1, padding: 0, overflow: 'hidden' }}
        >
          <ResizableTable 
            columns={columns}
            data={MOCK_ORDERS}
            onRowClick={(row) => console.log('Clicked order', row)}
          />
        </Widget>
      </Grid>
    </div>
  );
};

export default ACMEPage;
