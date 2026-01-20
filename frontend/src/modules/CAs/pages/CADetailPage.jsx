import React, { useState, useEffect } from 'react';
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
import { caService } from '../services/ca.service';
import './CADetailPage.css';

const CADetailPage = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('issued');
  const [ca, setCa] = useState(null);
  const [loading, setLoading] = useState(true);
  const [certs, setCerts] = useState([]);
  const [certsLoading, setCertsLoading] = useState(false);

  // Helper to render value or dash
  const renderValue = (val) => {
    if (val === null || val === undefined || val === '') return '-';
    return val;
  };

  // Helper for Organization/Country
  const renderOrg = (org, country) => {
    const parts = [org, country].filter(p => p);
    if (parts.length === 0) return '-';
    return parts.join(', ');
  };

  // Fetch CA Details
  useEffect(() => {
    const fetchCA = async () => {
        setLoading(true);
        try {
            const data = await caService.getById(id);
            setCa(data);
        } catch (error) {
            console.error("Failed to fetch CA:", error);
        } finally {
            setLoading(false);
        }
    };
    if (id) fetchCA();
  }, [id]);

  // Fetch Certificates when tab is active
  useEffect(() => {
    const fetchCerts = async () => {
        if (!id || activeTab !== 'issued') return;
        setCertsLoading(true);
        try {
            const response = await caService.getCertificates(id);
            setCerts(response.data || []);
        } catch (error) {
            console.error("Failed to fetch certs:", error);
        } finally {
            setCertsLoading(false);
        }
    };
    fetchCerts();
  }, [id, activeTab]);

  if (loading) return null; // Or loading spinner
  if (!ca) return <div style={{ padding: 20 }}>CA Not Found</div>;

  return (
    <div className="ca-detail-page" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <PageHeader 
        title={ca.descr || ca.commonName} 
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
                    <Text size="sm" fw={500}>{renderValue(ca.commonName || ca.descr)}</Text>
                </Group>
                <Group justify="space-between">
                    <Text size="sm" c="dimmed">Organization</Text>
                    <Text size="sm">{renderOrg(ca.org, ca.country)}</Text>
                </Group>
                <Group justify="space-between">
                    <Text size="sm" c="dimmed">Type</Text>
                    <Badge variant="outline" color="gray" size="xs">{ca.is_root ? 'Root CA' : 'Intermediate'}</Badge>
                </Group>
            </Stack>
        </Widget>

        <Widget className="col-4" title="Status & Key" icon={<Key size={18} className="icon-gradient-subtle" />}>
            <Stack gap="xs">
                    <Group justify="space-between">
                    <Text size="sm" c="dimmed">Status</Text>
                    <Badge color="green" variant="dot" size="sm">Active</Badge>
                </Group>
                <Group justify="space-between">
                    <Text size="sm" c="dimmed">Algorithm</Text>
                    <Text size="sm" className="mono-text">{renderValue(ca.keyAlgo)}</Text>
                </Group>
                <Group justify="space-between">
                    <Text size="sm" c="dimmed">Key Size</Text>
                    <Text size="xs" className="mono-text">{ca.keySize ? `${ca.keySize} bits` : '-'}</Text>
                </Group>
            </Stack>
        </Widget>

        <Widget className="col-4" title="Validity" icon={<CalendarCheck size={18} className="icon-gradient-subtle" />}>
            <Stack gap="xs">
                <Group justify="space-between">
                    <Text size="sm" c="dimmed">Valid From</Text>
                    <Text size="sm">{renderValue(ca.valid_from ? new Date(ca.valid_from).toLocaleDateString() : null)}</Text>
                </Group>
                <Group justify="space-between">
                    <Text size="sm" c="dimmed">Valid To</Text>
                    <Text size="sm">{renderValue(ca.valid_to ? new Date(ca.valid_to).toLocaleDateString() : null)}</Text>
                </Group>
                <Group justify="space-between">
                    <Text size="sm" c="dimmed">Next CRL Update</Text>
                    <Text size="sm" c={ca.crlStatus === 'Active' ? 'dimmed' : 'red'}>{renderValue(ca.nextCrlUpdate)}</Text>
                </Group>
            </Stack>
        </Widget>

        {/* Tabs for Issued Certs, CRLs, etc */}
        <Widget className="col-12" style={{ padding: 0, overflow: 'hidden', minHeight: '500px' }}>
            <Tabs value={activeTab} onChange={setActiveTab} style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
                <div style={{ padding: '0 var(--spacing-lg)', borderBottom: '1px solid var(--border-primary)' }}>
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
                                data={certs}
                                loading={certsLoading}
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
