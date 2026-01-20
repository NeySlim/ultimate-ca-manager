import React, { useState } from 'react';
import {
  Button,
  Group,
  Text,
  Badge,
  Tabs,
  ActionIcon,
  Tooltip,
} from '@mantine/core';
import {
  ShieldCheck,
  FileText,
  Globe,
  ArrowClockwise,
  DownloadSimple,
  CheckCircle,
  XCircle,
  ListDashes,
} from '@phosphor-icons/react';
import { PageHeader, Grid, Widget } from '../../../components/ui/Layout';
import StatWidget from '../../Dashboard/components/widgets/StatWidget';
import ResizableTable from '../../../components/ui/Layout/ResizableTable';
import './ValidationPage.css';

// Mock Data
const MOCK_CRLS = [
  {
    id: 1,
    issuer: 'Root CA - UCM Global',
    thisUpdate: '2024-03-20T00:00:00Z',
    nextUpdate: '2024-03-27T00:00:00Z',
    serial: '1024',
    entries: 12
  },
  {
    id: 2,
    issuer: 'Intermediate CA - Web Server',
    thisUpdate: '2024-03-20T06:00:00Z',
    nextUpdate: '2024-03-21T06:00:00Z',
    serial: '5521',
    entries: 5
  }
];

const MOCK_OCSP_LOGS = [
  {
    id: 1,
    serial: '1234-5678-90AB-CDEF',
    status: 'Good',
    requester: '192.168.1.105',
    timestamp: '2024-03-20T10:30:00Z',
    latency: '15ms'
  },
  {
    id: 2,
    serial: '9876-5432-10FE-DCBA',
    status: 'Revoked',
    requester: '10.0.0.52',
    timestamp: '2024-03-20T10:28:00Z',
    latency: '12ms'
  }
];

const ValidationPage = () => {
  const [activeTab, setActiveTab] = useState('crl');

  const crlColumns = [
    {
      key: 'issuer',
      label: 'Issuer Name',
      width: 250,
      render: (row) => (
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <ShieldCheck size={18} className="icon-gradient-subtle" style={{ marginRight: 8 }} />
          <Text size="sm" fw={500}>{row.issuer}</Text>
        </div>
      )
    },
    {
      key: 'thisUpdate',
      label: 'Last Update',
      width: 150,
      render: (row) => <Text size="sm">{new Date(row.thisUpdate).toLocaleDateString()}</Text>
    },
    {
      key: 'nextUpdate',
      label: 'Next Update',
      width: 150,
      render: (row) => <Text size="sm" c="dimmed">{new Date(row.nextUpdate).toLocaleDateString()}</Text>
    },
    {
      key: 'entries',
      label: 'Revoked Count',
      width: 120,
      render: (row) => <Badge variant="outline" color="gray" size="xs">{row.entries}</Badge>
    },
    {
      key: 'actions',
      label: 'Actions',
      width: 100,
      render: (row) => (
        <Group gap={4}>
          <Tooltip label="Download CRL">
            <ActionIcon size="sm" variant="light">
              <DownloadSimple size={16} />
            </ActionIcon>
          </Tooltip>
          <Tooltip label="Regenerate">
            <ActionIcon size="sm" variant="light" color="blue">
              <ArrowClockwise size={16} />
            </ActionIcon>
          </Tooltip>
        </Group>
      )
    }
  ];

  const ocspColumns = [
    {
      key: 'serial',
      label: 'Certificate Serial',
      width: 200,
      render: (row) => (
        <Text size="xs" className="mono-text" truncate>{row.serial}</Text>
      )
    },
    {
      key: 'status',
      label: 'Response',
      width: 100,
      render: (row) => (
        <Badge 
          color={row.status === 'Good' ? 'green' : 'red'} 
          variant="dot" 
          size="sm"
        >
          {row.status}
        </Badge>
      )
    },
    {
      key: 'requester',
      label: 'Requester IP',
      width: 150,
      render: (row) => <Text size="xs" c="dimmed">{row.requester}</Text>
    },
    {
      key: 'latency',
      label: 'Latency',
      width: 100,
      render: (row) => <Text size="xs">{row.latency}</Text>
    },
    {
      key: 'timestamp',
      label: 'Time',
      width: 150,
      render: (row) => <Text size="sm">{new Date(row.timestamp).toLocaleTimeString()}</Text>
    }
  ];

  return (
    <div className="validation-page" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <PageHeader 
        title="Validation Services" 
        actions={
          <Button variant="light" leftSection={<ArrowClockwise size={16} />} size="xs">
            Refresh All
          </Button>
        }
      />

      <Grid style={{ flex: 1, padding: '16px' }}>
        {/* Stats Row */}
        <div className="widget-1-3">
            <StatWidget
                icon={<FileText size={32} weight="duotone" className="icon-gradient-glow" />}
                value="2"
                label="Active CRLs"
                color="blue"
            />
        </div>
        <div className="widget-1-3">
            <StatWidget
                icon={<Globe size={32} weight="duotone" className="icon-gradient-glow" />}
                value="99.9%"
                label="OCSP Uptime"
                color="green"
            />
        </div>
        <div className="widget-1-3">
            <StatWidget
                icon={<CheckCircle size={32} weight="duotone" className="icon-gradient-glow" />}
                value="15ms"
                label="Avg Latency"
                color="cyan"
            />
        </div>

        <Widget className="widget-full" style={{ flex: 1, padding: 0, overflow: 'hidden' }}>
            <Tabs value={activeTab} onChange={setActiveTab} style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
                <div style={{ padding: '0 16px', borderBottom: '1px solid #333' }}>
                    <Tabs.List style={{ borderBottom: 'none' }}>
                        <Tabs.Tab value="crl" leftSection={<FileText size={16} />}>
                            Certificate Revocation Lists (CRL)
                        </Tabs.Tab>
                        <Tabs.Tab value="ocsp" leftSection={<Globe size={16} />}>
                            OCSP Responder
                        </Tabs.Tab>
                    </Tabs.List>
                </div>

                <div style={{ flex: 1, position: 'relative' }}>
                    <Tabs.Panel value="crl" style={{ height: '100%' }}>
                        <ResizableTable 
                            columns={crlColumns}
                            data={MOCK_CRLS}
                            onRowClick={(row) => console.log('Clicked CRL', row)}
                        />
                    </Tabs.Panel>
                    <Tabs.Panel value="ocsp" style={{ height: '100%' }}>
                        <ResizableTable 
                            columns={ocspColumns}
                            data={MOCK_OCSP_LOGS}
                            onRowClick={(row) => console.log('Clicked OCSP', row)}
                        />
                    </Tabs.Panel>
                </div>
            </Tabs>
        </Widget>
      </Grid>
    </div>
  );
};

export default ValidationPage;
