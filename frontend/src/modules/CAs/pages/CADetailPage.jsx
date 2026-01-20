import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Button,
  Group,
  Text,
  Badge,
  Stack,
  Tabs,
  ActionIcon,
  Tooltip,
} from '@mantine/core';
import {
  ShieldCheck,
  Certificate,
  Key,
  CalendarCheck,
  DownloadSimple,
  PencilSimple,
  Trash,
  ListDashes,
  ChartLineUp,
  FileText,
} from '@phosphor-icons/react';
import { PageHeader, Grid, Widget } from '../../../components/ui/Layout';
import StatWidget from '../../Dashboard/components/widgets/StatWidget';
import ResizableTable from '../../../components/ui/Layout/ResizableTable';
import CertificateTable from '../../Certificates/components/CertificateTable';
import './CADetailPage.css';

// Mock Data
const MOCK_CA_DETAILS = {
  1: {
    id: 1,
    name: 'Root CA - UCM Global',
    type: 'Root CA',
    status: 'Active',
    commonName: 'UCM Global Root CA G1',
    org: 'UCM Corp',
    country: 'US',
    validFrom: '2020-01-01',
    validTo: '2040-01-01',
    serial: '1234-5678-90AB-CDEF',
    keyAlgo: 'RSA 4096',
    issuedCount: 124,
    crlStatus: 'Active',
    nextCrlUpdate: '2024-03-27'
  }
};

const MOCK_ISSUED_CERTS = [
  {
    id: 101,
    commonName: 'web.internal.corp',
    status: 'Valid',
    serial: '5566-7788',
    issuer: 'UCM Global Root CA G1',
    issuedDate: '2023-01-15',
    expiryDate: '2024-01-15',
    ca: 'Root CA - UCM Global'
  },
  {
    id: 102,
    commonName: 'api.gateway.net',
    status: 'Valid',
    serial: '9900-1122',
    issuer: 'UCM Global Root CA G1',
    issuedDate: '2023-02-20',
    expiryDate: '2024-02-20',
    ca: 'Root CA - UCM Global'
  }
];

const CADetailPage = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('issued');
  const ca = MOCK_CA_DETAILS[1]; // Mock fallback

  return (
    <div className="ca-detail-page" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <PageHeader 
        title={ca.name} 
        backAction={() => navigate('/cas/tree')}
        actions={
            <Group gap="xs">
                <Button variant="light" leftSection={<DownloadSimple size={16} />} size="xs">
                    Download Cert
                </Button>
                <Button leftSection={<PencilSimple size={16} />} size="xs">
                    Edit CA
                </Button>
            </Group>
        }
      />

      <Grid>
        {/* Top Info Widgets */}
        <Widget className="col-4" title="Identity" icon={<ShieldCheck size={18} className="icon-gradient-subtle" />}>
            <Stack gap="xs">
                <Group justify="space-between">
                    <Text size="sm" c="dimmed">Common Name</Text>
                    <Text size="sm" fw={500}>{ca.commonName}</Text>
                </Group>
                <Group justify="space-between">
                    <Text size="sm" c="dimmed">Organization</Text>
                    <Text size="sm">{ca.org}, {ca.country}</Text>
                </Group>
                <Group justify="space-between">
                    <Text size="sm" c="dimmed">Type</Text>
                    <Badge variant="outline" color="gray" size="xs">{ca.type}</Badge>
                </Group>
            </Stack>
        </Widget>

        <Widget className="col-4" title="Status & Key" icon={<Key size={18} className="icon-gradient-subtle" />}>
            <Stack gap="xs">
                    <Group justify="space-between">
                    <Text size="sm" c="dimmed">Status</Text>
                    <Badge color="green" variant="dot" size="sm">{ca.status}</Badge>
                </Group>
                <Group justify="space-between">
                    <Text size="sm" c="dimmed">Algorithm</Text>
                    <Text size="sm" className="mono-text">{ca.keyAlgo}</Text>
                </Group>
                <Group justify="space-between">
                    <Text size="sm" c="dimmed">Serial</Text>
                    <Text size="xs" className="mono-text">{ca.serial}</Text>
                </Group>
            </Stack>
        </Widget>

        <Widget className="col-4" title="Validity" icon={<CalendarCheck size={18} className="icon-gradient-subtle" />}>
            <Stack gap="xs">
                <Group justify="space-between">
                    <Text size="sm" c="dimmed">Valid From</Text>
                    <Text size="sm">{ca.validFrom}</Text>
                </Group>
                <Group justify="space-between">
                    <Text size="sm" c="dimmed">Valid To</Text>
                    <Text size="sm">{ca.validTo}</Text>
                </Group>
                <Group justify="space-between">
                    <Text size="sm" c="dimmed">Next CRL Update</Text>
                    <Text size="sm" c={ca.crlStatus === 'Active' ? 'dimmed' : 'red'}>{ca.nextCrlUpdate}</Text>
                </Group>
            </Stack>
        </Widget>

        {/* Tabs for Issued Certs, CRLs, etc */}
        <Widget className="col-12" style={{ padding: 0, overflow: 'hidden', minHeight: '500px' }}>
            <Tabs value={activeTab} onChange={setActiveTab} style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
                <div style={{ padding: '0 16px', borderBottom: '1px solid #333' }}>
                    <Tabs.List style={{ borderBottom: 'none' }}>
                        <Tabs.Tab value="issued" leftSection={<Certificate size={16} />}>
                            Issued Certificates
                        </Tabs.Tab>
                        <Tabs.Tab value="crl" leftSection={<FileText size={16} />}>
                            CRL History
                        </Tabs.Tab>
                        <Tabs.Tab value="stats" leftSection={<ChartLineUp size={16} />}>
                            Statistics
                        </Tabs.Tab>
                    </Tabs.List>
                </div>

                <div style={{ flex: 1, position: 'relative' }}>
                    <Tabs.Panel value="issued" style={{ height: '100%' }}>
                            <CertificateTable 
                            data={MOCK_ISSUED_CERTS}
                            onRowClick={(row) => navigate(`/certificates/${row.id}`)}
                            />
                    </Tabs.Panel>
                    <Tabs.Panel value="crl" style={{ padding: '16px' }}>
                        <Text c="dimmed" size="sm">CRL History will be displayed here.</Text>
                    </Tabs.Panel>
                        <Tabs.Panel value="stats" style={{ padding: '16px' }}>
                        <Text c="dimmed" size="sm">Issuance statistics will be displayed here.</Text>
                    </Tabs.Panel>
                </div>
            </Tabs>
        </Widget>
      </Grid>
    </div>
  );
};

export default CADetailPage;
