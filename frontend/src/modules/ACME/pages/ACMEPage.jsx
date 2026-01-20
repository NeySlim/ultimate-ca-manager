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
  ListDashes,
  Copy,
  ChartLineUp
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

  const renderValue = (val) => {
    if (val === null || val === undefined || val === '') return '-';
    return val;
  };

  const columns = [
    {
      key: 'domain',
      label: 'Domain / Identifier',
      width: 250,
      render: (row) => (
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <Globe size={16} className="icon-gradient-subtle" style={{ marginRight: 8 }} />
          <Text size="sm" fw={500}>{renderValue(row.domain)}</Text>
        </div>
      )
    },
    {
      key: 'account',
      label: 'ACME Account',
      width: 200,
      render: (row) => <Text size="sm" c="dimmed">{renderValue(row.account)}</Text>
    },
    {
      key: 'method',
      label: 'Challenge',
      width: 100,
      render: (row) => <Badge variant="outline" size="xs">{renderValue(row.method)}</Badge>
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
          {renderValue(row.status)}
        </Badge>
      )
    },
    {
      key: 'expires',
      label: 'Expires',
      width: 120,
      render: (row) => <Text size="sm">{renderValue(row.expires)}</Text>
    }
  ];

  return (
    <div className="acme-page" style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <PageHeader 
        title="ACME Protocol" 
        actions={
          <Button variant="light" leftSection={<Gear size={16} />} size="xs">
            Settings
          </Button>
        }
      />

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden', padding: '12px', gap: '12px' }}>
        
        {/* LEFT COLUMN: Main Table (70%) */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, gap: '12px' }}>
             
             {/* Connection Info Widget */}
             <div className="widget-panel" style={{ background: 'var(--bg-panel)', border: '1px solid var(--border-color)', borderRadius: 'var(--control-radius)', padding: '12px' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    
                    {/* URL Section */}
                    <div>
                        <Text size="xs" weight={600} mb={4} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <Globe size={14} className="icon-gradient-subtle"/> Directory URL
                        </Text>
                        <div style={{ background: 'var(--bg-app)', padding: '6px 10px', borderRadius: 'var(--control-radius)', border: '1px solid var(--border-subtle)', display: 'flex', alignItems: 'center', gap: 8 }}>
                            <Text size="sm" style={{ fontFamily: 'var(--font-mono)', flex: 1 }}>
                            https://{window.location.hostname}:8443/acme/directory
                            </Text>
                            <Copy size={14} style={{ cursor: 'pointer', opacity: 0.7 }} onClick={() => navigator.clipboard.writeText(`https://${window.location.hostname}:8443/acme/directory`)} />
                        </div>
                    </div>

                    {/* Command Section */}
                    <div>
                        <Text size="xs" weight={600} mb={4} color="dimmed">Client Example (Certbot)</Text>
                        <div style={{ background: 'var(--bg-element)', padding: '6px 10px', borderRadius: 'var(--control-radius)', border: '1px solid var(--border-subtle)', fontFamily: 'var(--font-mono)', fontSize: 'var(--font-size-label)', color: 'var(--text-secondary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            certbot register --server https://{window.location.hostname}:8443/acme/directory
                        </div>
                    </div>

                </div>
             </div>

             <Widget 
              title="Recent Orders" 
              icon={<ListDashes size={18} className="icon-gradient-subtle" />} 
              className="widget-full" 
              style={{ flex: 1, padding: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}
            >
              <div style={{ flex: 1, minHeight: 0 }}>
                 <ResizableTable 
                    columns={columns}
                    data={orders}
                    onRowClick={(row) => console.log('Clicked order', row)}
                    emptyMessage="No ACME orders found"
                  />
              </div>
            </Widget>
        </div>

        {/* RIGHT COLUMN: Stats & Help (30%) */}
        <div style={{ width: '320px', display: 'flex', flexDirection: 'column', gap: '12px', flexShrink: 0 }}>
            
            {/* Compact Stats */}
            <StatWidget
                icon={<CheckCircle size={24} className="icon-gradient-subtle" />}
                value={stats.active_accounts}
                label="Active Accounts"
                color="blue"
                compact
            />
            <StatWidget
                icon={<ChartLineUp size={24} className="icon-gradient-subtle" />}
                value={stats.total_orders}
                label="Total Orders"
                subLabel={`${stats.pending_orders} pending`}
                color="green"
                compact
            />
            <StatWidget
                icon={<XCircle size={24} className="icon-gradient-subtle" />}
                value={stats.invalid_orders}
                label="Failed Challenges"
                color="red"
                compact
            />
        </div>

      </div>
    </div>
  );
};

export default ACMEPage;
