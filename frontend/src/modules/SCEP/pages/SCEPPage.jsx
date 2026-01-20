import React, { useState, useEffect } from 'react';
import {
  Button,
  Group,
  Text,
  Badge,
} from '@mantine/core';
import {
  Devices,
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
  const [config, setConfig] = useState(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [statsData, requestsData, configData] = await Promise.all([
        ScepService.getStats(),
        ScepService.getRequests(),
        ScepService.getConfig()
      ]);
      setStats(statsData);
      setRequests(requestsData);
      setConfig(configData);
    } catch (error) {
      console.error("Failed to load SCEP data", error);
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
      key: 'transaction_id',
      label: 'Transaction ID',
      width: 200,
      render: (row) => (
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <Devices size={16} className="icon-gradient-subtle" style={{ marginRight: 8 }} />
          <Text size="sm" fw={500}>{renderValue(row.transaction_id || row.transactionId)}</Text>
        </div>
      )
    },
    {
      key: 'subject',
      label: 'Subject',
      width: 250,
      render: (row) => <Text size="sm">{renderValue(row.subject)}</Text>
    },
    {
      key: 'client_ip',
      label: 'Client IP',
      width: 120,
      render: (row) => <Text size="sm" c="dimmed">{renderValue(row.client_ip)}</Text>
    },
    {
      key: 'status',
      label: 'Status',
      width: 100,
      render: (row) => (
        <Badge 
          color={row.status === 'approved' ? 'green' : row.status === 'rejected' ? 'red' : 'yellow'} 
          variant="dot"
          size="sm"
        >
          {renderValue(row.status)}
        </Badge>
      )
    },
    {
      key: 'created_at',
      label: 'Requested At',
      width: 150,
      render: (row) => <Text size="sm">{renderValue(row.created_at)}</Text>
    }
  ];

  return (
    <div className="scep-page" style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <PageHeader 
        title="SCEP Server" 
        actions={
          <Button variant="light" leftSection={<Gear size={16} />} size="xs">
            Config
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
                            <Devices size={14} className="icon-gradient-subtle"/> SCEP URL
                        </Text>
                        <div style={{ background: 'var(--bg-app)', padding: '6px 10px', borderRadius: 'var(--control-radius)', border: '1px solid var(--border-subtle)', display: 'flex', alignItems: 'center', gap: 8 }}>
                            <Text size="sm" style={{ fontFamily: 'var(--font-mono)', flex: 1 }}>
                            http://{window.location.hostname}:80/scep/pkiclient.exe
                            </Text>
                            <Copy size={14} style={{ cursor: 'pointer', opacity: 0.7 }} onClick={() => navigator.clipboard.writeText(`http://${window.location.hostname}:80/scep/pkiclient.exe`)} />
                        </div>
                    </div>

                    {/* Info Section */}
                    <div>
                        <Text size="xs" weight={600} mb={4} color="dimmed">Configuration Status</Text>
                        <div style={{ background: 'var(--bg-element)', padding: '6px 10px', borderRadius: 'var(--control-radius)', fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-secondary)' }}>
                             Auto-Approve: <span style={{ color: config?.auto_approve ? 'var(--mantine-color-green-5)' : 'var(--mantine-color-red-5)' }}>{config?.auto_approve ? 'Enabled' : 'Disabled'}</span> • RFC 8894
                        </div>
                    </div>

                </div>
             </div>

             <Widget 
              title="Enrollment Requests" 
              icon={<ListDashes size={18} className="icon-gradient-subtle" />} 
              className="widget-full" 
              style={{ flex: 1, padding: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}
            >
              <div style={{ flex: 1, minHeight: 0 }}>
                 <ResizableTable 
                    columns={columns}
                    data={requests}
                    onRowClick={(row) => console.log('Clicked request', row)}
                    emptyMessage="No SCEP requests found"
                  />
              </div>
            </Widget>
        </div>

        {/* RIGHT COLUMN: Stats & Help (30%) */}
        <div style={{ width: '320px', display: 'flex', flexDirection: 'column', gap: '12px', flexShrink: 0 }}>
            
            {/* Compact Stats */}
            <StatWidget
                icon={<CheckCircle size={24} className="icon-gradient-subtle" />}
                value={stats.approved}
                label="Enrolled Devices"
                color="blue"
                compact
            />
            <StatWidget
                icon={<Devices size={24} className="icon-gradient-subtle" />}
                value={stats.total}
                label="Total Requests"
                subLabel={`${stats.pending} pending`}
                color="green"
                compact
            />
            <StatWidget
                icon={<XCircle size={24} className="icon-gradient-subtle" />}
                value={stats.rejected}
                label="Rejected"
                color="red"
                compact
            />
        </div>

      </div>
    </div>
  );
};

export default SCEPPage;
