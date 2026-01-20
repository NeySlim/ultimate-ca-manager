import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Button,
  Group,
  Badge,
  Text,
  Paper,
  Stack,
  Code,
  Divider,
  Tabs,
  ActionIcon,
} from '@mantine/core';
import { useModals } from '@mantine/modals';
import {
  CaretLeft,
  PenNib,
  Trash,
  DownloadSimple,
  Copy,
  Certificate,
  IdentificationCard,
  Key,
} from '@phosphor-icons/react';
import { PageHeader, Grid, Widget } from '../../../components/ui/Layout';
import SignCSRModal from '../components/SignCSRModal';
import './CSRDetailPage.css';

// Mock Data
const MOCK_CSR_DETAILS = {
  1: {
    id: 1,
    commonName: 'web.internal.corp',
    org: 'MyCorp Internal',
    ou: 'IT Operations',
    city: 'San Francisco',
    state: 'CA',
    country: 'US',
    email: 'admin@internal.corp',
    algo: 'RSA 2048',
    status: 'Pending',
    created: '2024-03-15T10:30:00Z',
    requester: 'admin',
    pem: `-----BEGIN CERTIFICATE REQUEST-----
MIICzjCCAbYCAQAwgYgxCzAJBgNVBAYTAlVTMQswCQYDVQQIDAJDQTESMBAGA1UE
BwwJU2FuIEZyYW4...
(truncated for UI demo)
...-----END CERTIFICATE REQUEST-----`,
    sans: ['www.web.internal.corp', 'api.web.internal.corp'],
    keyUsage: ['Digital Signature', 'Key Encipherment'],
    extendedKeyUsage: ['Server Auth', 'Client Auth']
  }
};

const CSRDetailPage = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const modals = useModals();
  const csr = MOCK_CSR_DETAILS[id] || MOCK_CSR_DETAILS[1]; // Fallback to 1 for demo

  const handleSignClick = () => {
    modals.openModal({
        title: 'Sign Certificate Request',
        centered: true,
        children: (
            <SignCSRModal 
                csr={csr}
                onSign={(data) => {
                    console.log('Signed with:', data);
                    modals.closeAll();
                    navigate('/certificates');
                }}
                onCancel={() => modals.closeAll()}
            />
        )
    });
  };

  return (
    <div className="csr-detail-page">
      <PageHeader 
        title={`CSR: ${csr.commonName}`} 
        backAction={() => navigate('/csrs')}
        actions={
          <Group gap="xs">
            <Button 
              variant="light" 
              color="red" 
              leftSection={<Trash size={16} />} 
              size="xs"
            >
              Reject
            </Button>
            <Button 
              leftSection={<PenNib size={16} />} 
              size="xs"
              onClick={handleSignClick}
            >
              Sign Request
            </Button>
          </Group>
        }
      />

      <Grid className="csr-detail-grid">
        <Widget title="Request Information" icon={<IdentificationCard size={20} className="icon-gradient-subtle" />}>
          <Stack gap="md">
            <Group justify="space-between">
              <Text size="sm" c="dimmed">Status</Text>
              <Badge 
                color={csr.status === 'Signed' ? 'green' : 'blue'} 
                variant="dot"
              >
                {csr.status}
              </Badge>
            </Group>
            
            <Divider />
            
            <Group justify="space-between">
              <Text size="sm" c="dimmed">Common Name</Text>
              <Text size="sm" fw={500}>{csr.commonName}</Text>
            </Group>
            <Group justify="space-between">
              <Text size="sm" c="dimmed">Organization</Text>
              <Text size="sm">{csr.org}</Text>
            </Group>
            <Group justify="space-between">
              <Text size="sm" c="dimmed">Organizational Unit</Text>
              <Text size="sm">{csr.ou}</Text>
            </Group>
            <Group justify="space-between">
              <Text size="sm" c="dimmed">Location</Text>
              <Text size="sm">{csr.city}, {csr.state}, {csr.country}</Text>
            </Group>
          </Stack>
        </Widget>

        <Widget title="Key Details" icon={<Key size={20} className="icon-gradient-subtle" />}>
          <Stack gap="md">
            <Group justify="space-between">
              <Text size="sm" c="dimmed">Algorithm</Text>
              <Badge variant="outline">{csr.algo}</Badge>
            </Group>
            
            <Divider />
            
            <Text size="sm" c="dimmed">Subject Alternative Names</Text>
            <Group gap="xs">
              {csr.sans.map(san => (
                <Badge key={san} variant="filled" color="dark" size="sm">
                  {san}
                </Badge>
              ))}
            </Group>

            <Text size="sm" c="dimmed" mt="sm">Key Usage</Text>
            <Group gap="xs">
              {csr.keyUsage.map(usage => (
                <Badge key={usage} variant="dot" variant="outline" size="sm">
                  {usage}
                </Badge>
              ))}
            </Group>
          </Stack>
        </Widget>

        <Widget title="Raw CSR" icon={<Certificate size={20} className="icon-gradient-subtle" />} className="widget-full">
          <Paper withBorder p="xs" bg="#0d0d0d" style={{ position: 'relative' }}>
            <ActionIcon 
              variant="subtle" 
              variant="outline" 
              size="sm" 
              style={{ position: 'absolute', top: 5, right: 5 }}
            >
              <Copy size={14} />
            </ActionIcon>
            <Code block color="dark" style={{ fontSize: 'var(--font-size-label)', whiteSpace: 'pre-wrap' }}>
              {csr.pem}
            </Code>
          </Paper>
        </Widget>
      </Grid>
    </div>
  );
};

export default CSRDetailPage;
