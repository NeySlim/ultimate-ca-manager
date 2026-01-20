import React, { useState, useEffect } from 'react';
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
import { AcmeService } from '../services/acme.service';
import './ACMEPage.css';

const ACMEPage = () => {
  const [stats, setStats] = useState({
    active_accounts: 0,
    total_orders: 0,
    pending_orders: 0,
    valid_orders: 0,
    invalid_orders: 0
  });
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [statsData, ordersData] = await Promise.all([
        AcmeService.getStats(),
        AcmeService.getOrders()
      ]);
      setStats(statsData);
      setOrders(ordersData);
    } catch (error) {
      console.error("Failed to load ACME data", error);
    } finally {
      setLoading(false);
    }
  };

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
            value={stats.active_accounts}
            label="Active Accounts"
            color="blue"
          />
        </div>
        <div className="widget-1-3">
          <StatWidget
            icon={<CheckCircle size={32} weight="duotone" className="icon-gradient-glow" />}
            value={stats.total_orders}
            label="Total Orders"
            subLabel={`${stats.pending_orders} pending`}
            color="green"
          />
        </div>
        <div className="widget-1-3">
          <StatWidget
            icon={<XCircle size={32} weight="duotone" className="icon-gradient-glow" />}
            value={stats.invalid_orders}
            label="Failed Challenges"
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
            data={orders}
            onRowClick={(row) => console.log('Clicked order', row)}
            emptyMessage="No ACME orders found"
          />
        </Widget>
      </Grid>
    </div>
  );
};

export default ACMEPage;
