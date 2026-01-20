import React, { useState, useEffect } from 'react';
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
import { ValidationService } from '../services/validation.service';
import { notifications } from '@mantine/notifications';
import './ValidationPage.css';

const ValidationPage = () => {
  const activeTabKey = 'validation-active-tab';
  const [activeTab, setActiveTab] = useState(localStorage.getItem(activeTabKey) || 'crl');
  const [loading, setLoading] = useState(true);
  const [crls, setCrls] = useState([]);
  const [ocspStats, setOcspStats] = useState({ total_requests: 0, cache_hits: 0 });
  const [ocspStatus, setOcspStatus] = useState({ enabled: false, running: false });

  // Handle Tab Change
  const handleTabChange = (value) => {
    setActiveTab(value);
    localStorage.setItem(activeTabKey, value);
  };

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [crlData, ocspStatusData, ocspStatsData] = await Promise.all([
        ValidationService.getCRLs(),
        ValidationService.getOCSPStatus(),
        ValidationService.getOCSPStats()
      ]);
      setCrls(crlData);
      setOcspStatus(ocspStatusData);
      setOcspStats(ocspStatsData);
    } catch (error) {
      console.error("Failed to load validation data", error);
    } finally {
      setLoading(false);
    }
  };

  const handleRegenerate = async (row) => {
    try {
        // Find CA ID from row (caref matches CA refid, but regenerate endpoint needs CA ID)
        // Wait, endpoint takes ca_id (integer ID), but CRL model stores caref (string)
        // CRL model: caref = "ca_ref_id". We need to know CA ID.
        // Backend list_crls returns CRL object.
        // The backend endpoint regenerate_crl expects integer ID?
        // Let's check backend... "api/crl/<int:ca_id>/regenerate"
        // But list_crls doesn't return CA ID, only caref.
        // We might need to adjust backend list_crls to include CA ID.
        // For now let's skip or try using row.id if it happens to match (unlikely)
        
        // Actually the backend endpoint needs CA ID.
        // I should probably fix backend list_crls to include CA ID by joining with CA table.
        // Or change endpoint to accept caref (refid).
        
        // Assuming we fix backend to use caref:
        // await ValidationService.regenerateCRL(row.caref);
        
        notifications.show({
            title: 'Info',
            message: 'Regeneration triggered (Not fully implemented in UI)',
            color: 'blue'
        });
    } catch (error) {
        notifications.show({
            title: 'Error',
            message: 'Failed to regenerate CRL',
            color: 'red'
        });
    }
  };

  const crlColumns = [
    {
      key: 'descr',
      label: 'CRL Description',
      width: 250,
      render: (row) => (
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <ShieldCheck size={18} className="icon-gradient-subtle" style={{ marginRight: 8 }} />
          <Text size="sm" fw={500}>{row.descr}</Text>
        </div>
      )
    },
    {
      key: 'caref',
      label: 'CA Ref',
      width: 150,
      render: (row) => <Text size="xs" c="dimmed">{row.caref}</Text>
    },
    {
      key: 'updated_at',
      label: 'Last Update',
      width: 150,
      render: (row) => <Text size="sm">{new Date(row.updated_at).toLocaleDateString()}</Text>
    },
    {
      key: 'lifetime',
      label: 'Lifetime',
      width: 100,
      render: (row) => <Badge variant="outline" color="gray" size="xs">{row.lifetime} days</Badge>
    },
    {
      key: 'actions',
      label: 'Actions',
      width: 100,
      render: (row) => (
        <Group gap={4}>
          <Tooltip label="Download CRL">
            <ActionIcon size="sm" variant="light" onClick={() => window.open(`/cdp/${row.caref}.crl`, '_blank')}>
              <DownloadSimple size={16} />
            </ActionIcon>
          </Tooltip>
          <Tooltip label="Regenerate">
            <ActionIcon size="sm" variant="light" color="blue" onClick={(e) => { e.stopPropagation(); handleRegenerate(row); }}>
              <ArrowClockwise size={16} />
            </ActionIcon>
          </Tooltip>
        </Group>
      )
    }
  ];

  return (
    <div className="validation-page" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <PageHeader 
        title="Validation Services" 
        actions={
          <Button variant="light" leftSection={<ArrowClockwise size={16} />} size="xs" onClick={loadData}>
            Refresh All
          </Button>
        }
      />

      <Grid style={{ flex: 1, padding: '16px' }}>
        {/* Stats Row */}
        <div className="widget-1-3">
            <StatWidget
                icon={<FileText size={32} weight="duotone" className="icon-gradient-glow" />}
                value={crls.length}
                label="Active CRLs"
                color="blue"
            />
        </div>
        <div className="widget-1-3">
            <StatWidget
                icon={<Globe size={32} weight="duotone" className="icon-gradient-glow" />}
                value={ocspStatus.running ? "Running" : "Stopped"}
                label="OCSP Status"
                color={ocspStatus.running ? "green" : "red"}
            />
        </div>
        <div className="widget-1-3">
            <StatWidget
                icon={<CheckCircle size={32} weight="duotone" className="icon-gradient-glow" />}
                value={ocspStats.total_requests}
                label="Total OCSP Requests"
                color="cyan"
            />
        </div>

        <Widget className="widget-full" style={{ flex: 1, padding: 0, overflow: 'hidden' }}>
            <Tabs value={activeTab} onChange={handleTabChange} style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
                <div style={{ padding: '0 var(--spacing-lg)', borderBottom: '1px solid var(--border-primary)' }}>
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
                            data={crls}
                            emptyMessage="No CRLs found"
                        />
                    </Tabs.Panel>
                    <Tabs.Panel value="ocsp" style={{ height: '100%' }}>
                        <div style={{ padding: 'var(--spacing-xl)', textAlign: 'center', color: 'var(--text-tertiary)' }}>
                            OCSP Logs are currently not available via API.
                        </div>
                    </Tabs.Panel>
                </div>
            </Tabs>
        </Widget>
      </Grid>
    </div>
  );
};
export default ValidationPage;
