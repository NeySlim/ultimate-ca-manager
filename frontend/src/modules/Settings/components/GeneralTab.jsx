import React, { useState, useEffect } from 'react';
import { Card, Text, Group, Badge, Button, Stack, Loader } from '@mantine/core';
import { HardDrives, Circuitry, CheckCircle, Warning, Info, PenNib } from '@phosphor-icons/react';
import { api } from '../../../core/api/client';

const GeneralTab = () => {
  const [info, setInfo] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // In a real implementation, this would come from an API
    // For now we mock it or fetch partial data
    setTimeout(() => {
        setInfo({
            version: '2.0.0-beta',
            port: window.location.port || '8443',
            dbType: 'SQLite',
            features: {
                crl: true,
                ocsp: true,
                scep: true,
                acme: true
            }
        });
        setLoading(false);
    }, 500);
  }, []);

  if (loading) {
      return <div style={{ padding: 20, textAlign: 'center' }}><Loader size="sm" /></div>;
  }

  return (
    <Stack spacing="lg">
      <Card withBorder padding="lg" radius="md">
        <Group position="apart" mb="md">
          <Group>
            <HardDrives size={24} className="icon-gradient-subtle" />
            <Text weight={600} size="lg">System Information</Text>
          </Group>
          <Button variant="subtle" size="xs" leftSection={<PenNib size={16} />}>
            Edit Configuration
          </Button>
        </Group>
        
        <Stack spacing="sm">
            <Group position="apart" className="detail-row">
                <Text color="dimmed" size="sm">Version</Text>
                <Text weight={500}>{info.version}</Text>
            </Group>
            <Group position="apart" className="detail-row">
                <Text color="dimmed" size="sm">HTTPS Port</Text>
                <Text weight={500}>{info.port}</Text>
            </Group>
            <Group position="apart" className="detail-row">
                <Text color="dimmed" size="sm">Database</Text>
                <Text weight={500}>{info.dbType}</Text>
            </Group>
             <Group position="apart" className="detail-row">
                <Text color="dimmed" size="sm">Active Features</Text>
                <Group spacing={8}>
                    {info.features.crl && <Badge size="sm" color="green" variant="light">CRL</Badge>}
                    {info.features.ocsp && <Badge size="sm" color="green" variant="light">OCSP</Badge>}
                    {info.features.scep && <Badge size="sm" color="blue" variant="light">SCEP</Badge>}
                    {info.features.acme && <Badge size="sm" color="blue" variant="light">ACME</Badge>}
                </Group>
            </Group>
        </Stack>
      </Card>
    </Stack>
  );
};

export default GeneralTab;
