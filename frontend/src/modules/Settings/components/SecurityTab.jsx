import React, { useState, useEffect } from 'react';
import { Card, Text, Group, Badge, Button, Stack, Loader, Radio, Select, Alert, Modal } from '@mantine/core';
import { ShieldCheck, LockKey, ArrowsClockwise, Warning, Check, Info } from '@phosphor-icons/react';
import { useDisclosure } from '@mantine/hooks';
import { api } from '../../../core/api/client';

const SecurityTab = () => {
  const [certInfo, setCertInfo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [source, setSource] = useState('auto');
  const [candidates, setCandidates] = useState([]);
  const [selectedCert, setSelectedCert] = useState(null);
  const [applying, setApplying] = useState(false);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
      try {
        const [infoRes, candidatesRes] = await Promise.all([
            api.get('/system/https/cert-info'),
            api.get('/certificates?type=server_cert') // Hypothetical filter
        ]);
        
        setCertInfo(infoRes.data);
        setSource(infoRes.data.source || 'auto');
        
        // Transform candidates for select
        if (candidatesRes.items) {
            setCandidates(candidatesRes.items.map(c => ({
                value: c.id.toString(),
                label: `${c.common_name} (Expires: ${new Date(c.not_after).toLocaleDateString()})`
            })));
        }
      } catch (err) {
          console.error("Failed to load security info", err);
      } finally {
          setLoading(false);
      }
  };

  const handleApply = async () => {
    if (source === 'managed' && !selectedCert) return;

    if (!window.confirm("Applying a new certificate will restart the UCM service. You may need to refresh the page. Continue?")) {
        return;
    }

    setApplying(true);
    try {
        if (source === 'auto') {
            await api.post('/system/https/regenerate');
        } else {
            await api.post('/system/https/apply', { cert_id: selectedCert });
        }
        alert("Certificate applied. Service is restarting...");
    } catch (err) {
        alert("Failed to apply certificate: " + err.message);
    } finally {
        setApplying(false);
    }
  };

  if (loading) return <div className="spinner" />;

  return (
    <Stack spacing="lg">
      {/* HTTPS Certificate */}
      <Card withBorder padding="lg" radius="md">
        <Group position="apart" mb="md">
          <Group>
            <LockKey size={24} className="icon-gradient-subtle" />
            <Text weight={600} size="lg">HTTPS Certificate</Text>
          </Group>
          <Badge color={certInfo?.type === 'Self-Signed' ? 'orange' : 'green'}>{certInfo?.type}</Badge>
        </Group>

        <Stack spacing="md">
            <Alert icon={<Info size={16} />} color="blue" variant="light">
                Configure the certificate used for the UCM web interface (port 8443).
            </Alert>

            {/* Current Info */}
            <Card withBorder radius="sm" p="sm" style={{ background: 'var(--mantine-color-gray-0)' }}>
                <Stack spacing="xs">
                    <Text size="xs" weight={700} transform="uppercase" color="dimmed">Current Certificate</Text>
                    <Group position="apart">
                        <Text size="sm" color="dimmed">Subject:</Text>
                        <Text size="sm" weight={500}>{certInfo?.subject}</Text>
                    </Group>
                    <Group position="apart">
                        <Text size="sm" color="dimmed">Expires:</Text>
                        <Text size="sm" weight={500}>{certInfo?.expires}</Text>
                    </Group>
                </Stack>
            </Card>

            <Text weight={500} size="sm" mt="sm">Certificate Source</Text>
            <Radio.Group value={source} onChange={setSource} name="certSource">
                <Stack spacing="sm">
                    <Radio value="auto" label={
                        <div>
                            <Text size="sm" weight={500}>Auto-generated (Self-signed)</Text>
                            <Text size="xs" color="dimmed">Use the system generated certificate (default)</Text>
                        </div>
                    } />
                    <Radio value="managed" label={
                        <div>
                            <Text size="sm" weight={500}>UCM Managed Certificate</Text>
                            <Text size="xs" color="dimmed">Select a valid server certificate from the inventory</Text>
                        </div>
                    } />
                </Stack>
            </Radio.Group>

            {source === 'managed' && (
                <Select
                    label="Select Certificate"
                    placeholder="Choose a certificate..."
                    data={candidates}
                    value={selectedCert}
                    onChange={setSelectedCert}
                    searchable
                    nothingFound="No server certificates found"
                />
            )}

            <Group mt="md">
                <Button 
                    leftSection={<Check size={16} />} 
                    onClick={handleApply} 
                    loading={applying}
                >
                    Apply Certificate
                </Button>
                {source === 'auto' && (
                    <Button 
                        variant="default" 
                        leftSection={<ArrowsClockwise size={16} />}
                        onClick={handleApply}
                        loading={applying}
                    >
                        Regenerate
                    </Button>
                )}
            </Group>
        </Stack>
      </Card>

      {/* mTLS Configuration */}
      <Card withBorder padding="lg" radius="md">
         <Group position="apart" mb="md">
          <Group>
            <ShieldCheck size={24} className="icon-gradient-subtle" />
            <Text weight={600} size="lg">mTLS Authentication</Text>
          </Group>
          <Badge variant="outline">Disabled</Badge>
        </Group>
        <Text size="sm" color="dimmed" mb="md">
            Require client certificates for access. Requires a reverse proxy (Nginx/Apache) for browser support.
        </Text>
        <Button variant="light" component="a" href="/config/mtls">
            Configure mTLS
        </Button>
      </Card>

      {/* OPNsense Import */}
      <Card withBorder padding="lg" radius="md" id="opnsense-import">
         <Group mb="md">
            <ArrowsClockwise size={24} className="icon-gradient-subtle" />
            <Text weight={600} size="lg">Import from OPNsense</Text>
         </Group>
         
         <Stack spacing="md">
             <Alert icon={<Info size={16} />} color="blue" variant="light">
                 Import existing Certificate Authorities and Certificates from an OPNsense backup XML file.
             </Alert>

             <Group>
                 <Button variant="default">Upload config.xml</Button>
                 <Text size="xs" color="dimmed">Supported: CA, Certs, CRLs</Text>
             </Group>
         </Stack>
      </Card>
    </Stack>
  );
};

export default SecurityTab;
