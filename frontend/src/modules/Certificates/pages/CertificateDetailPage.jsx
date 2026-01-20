import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Container,
  Card,
  Badge,
  Button,
  Group,
  Text,
  Stack,
  Textarea,
  Tabs,
  Grid,
  CopyButton,
  ActionIcon,
  Tooltip,
  Divider,
  Box,
  SimpleGrid,
} from '@mantine/core';
import {
  ArrowLeft,
  Download,
  Copy,
  Check,
  Trash,
  ArrowClockwise,
  LockKey,
  Calendar,
  Hash,
} from '@phosphor-icons/react';
import { CertificateService } from '../services/certificates.service';
import './CertificateDetailPage.css';

const CertificateDetailPage = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [certificate, setCertificate] = useState(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const loadCertificate = async () => {
      try {
        setLoading(true);
        const cert = await CertificateService.getById(id);
        setCertificate(cert);
      } catch (error) {
        console.error('Failed to load certificate', error);
      } finally {
        setLoading(false);
      }
    };

    loadCertificate();
  }, [id]);

  const handleDownload = () => {
    if (certificate) {
      const element = document.createElement('a');
      element.setAttribute('href', 'data:text/plain;charset=utf-8,' + encodeURIComponent(certificate.pem));
      element.setAttribute('download', `${certificate.commonName}.pem`);
      element.style.display = 'none';
      document.body.appendChild(element);
      element.click();
      document.body.removeChild(element);
    }
  };

  const handleRevoke = () => {
    if (window.confirm('Are you sure you want to revoke this certificate?')) {
      // Call revoke endpoint
      console.log('Revoking certificate', id);
    }
  };

  const handleRenew = () => {
    if (window.confirm('Generate a renewal request for this certificate?')) {
      // Call renew endpoint
      console.log('Renewing certificate', id);
    }
  };

  if (loading) {
    return (
      <Container size="xl" className="certificate-detail-page">
        <Text>Loading certificate details...</Text>
      </Container>
    );
  }

  if (!certificate) {
    return (
      <Container size="xl" className="certificate-detail-page">
        <Text color="red">Certificate not found</Text>
      </Container>
    );
  }

  const getStatusColor = (status) => {
    switch (status) {
      case 'Valid':
        return 'green';
      case 'Warning':
        return 'yellow';
      case 'Expired':
        return 'red';
      case 'Revoked':
        return 'gray';
      default:
        return 'blue';
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return '-';
    try {
      return new Date(dateString).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return dateString;
    }
  };

  return (
    <Container size="xl" className="certificate-detail-page">
      {/* Header */}
      <Group justify="space-between" mb="lg" mt="lg">
        <Group gap="md">
          <ActionIcon
            variant="light"
            onClick={() => navigate('/certificates')}
            title="Back to certificates"
          >
            <ArrowLeft size={18} />
          </ActionIcon>
          <div>
            <Text fw={700} size="lg">
              {certificate.commonName}
            </Text>
            <Badge color={getStatusColor(certificate.status)} variant="dot">
              {certificate.status}
            </Badge>
          </div>
        </Group>

        <Group gap="sm">
          <Tooltip label="Download Certificate">
            <Button
              leftSection={<Download size={16} />}
              variant="default"
              onClick={handleDownload}
            >
              Download
            </Button>
          </Tooltip>
          <Tooltip label="Renew Certificate">
            <Button
              leftSection={<ArrowClockwise size={16} />}
              variant="default"
              onClick={handleRenew}
            >
              Renew
            </Button>
          </Tooltip>
          <Tooltip label="Revoke Certificate">
            <Button
              leftSection={<Trash size={16} />}
              color="red"
              variant="light"
              onClick={handleRevoke}
            >
              Revoke
            </Button>
          </Tooltip>
        </Group>
      </Group>

      <Divider my="lg" />

      {/* Tabbed Content */}
      <Tabs defaultValue="general" className="certificate-tabs">
        <Tabs.List>
          <Tabs.Tab value="general">General Info</Tabs.Tab>
          <Tabs.Tab value="subject">Subject</Tabs.Tab>
          <Tabs.Tab value="issuer">Issuer</Tabs.Tab>
          <Tabs.Tab value="validity">Validity</Tabs.Tab>
          <Tabs.Tab value="extensions">Extensions</Tabs.Tab>
          <Tabs.Tab value="pem">PEM</Tabs.Tab>
        </Tabs.List>

        {/* General Info Tab */}
        <Tabs.Panel value="general" pt="md">
          <Stack gap="md">
            <Card withBorder className="info-card">
              <Stack gap="lg">
                <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="lg">
                  <div>
                    <Group gap="xs" mb="xs">
                      <Hash size={16} color="#888" />
                      <Text size="sm" fw={600} c="dimmed">
                        Serial Number
                      </Text>
                    </Group>
                    <Textarea
                      value={certificate.serial}
                      readOnly
                      minRows={2}
                      className="mono-textarea"
                    />
                    <CopyButton value={certificate.serial} timeout={1000}>
                      {({ copied }) => (
                        <Tooltip label={copied ? 'Copied' : 'Copy'} withArrow position="right">
                          <ActionIcon
                            color={copied ? 'green' : 'gray'}
                            variant="subtle"
                            size="sm"
                            mt="xs"
                          >
                            {copied ? <Check size={16} /> : <Copy size={16} />}
                          </ActionIcon>
                        </Tooltip>
                      )}
                    </CopyButton>
                  </div>

                  <div>
                    <Group gap="xs" mb="xs">
                      <LockKey size={16} color="#888" />
                      <Text size="sm" fw={600} c="dimmed">
                        Algorithm
                      </Text>
                    </Group>
                    <Text size="sm">{certificate.algorithm}</Text>
                  </div>

                  <div>
                    <Group gap="xs" mb="xs">
                      <Text size="sm" fw={600} c="dimmed">
                        Key Size
                      </Text>
                    </Group>
                    <Text size="sm">{certificate.keySize} bits</Text>
                  </div>

                  <div>
                    <Group gap="xs" mb="xs">
                      <Text size="sm" fw={600} c="dimmed">
                        Version
                      </Text>
                    </Group>
                    <Text size="sm">{certificate.version}</Text>
                  </div>

                  <div>
                    <Group gap="xs" mb="xs">
                      <Text size="sm" fw={600} c="dimmed">
                        Certificate Authority
                      </Text>
                    </Group>
                    <Text size="sm">{certificate.ca}</Text>
                  </div>

                  <div>
                    <Group gap="xs" mb="xs">
                      <Text size="sm" fw={600} c="dimmed">
                        Thumbprint (SHA-1)
                      </Text>
                    </Group>
                    <Text size="xs" className="mono-text" mt="xs">
                      {certificate.thumbprint}
                    </Text>
                  </div>
                </SimpleGrid>
              </Stack>
            </Card>
          </Stack>
        </Tabs.Panel>

        {/* Subject Tab */}
        <Tabs.Panel value="subject" pt="md">
          <Card withBorder className="info-card">
            <Stack gap="md">
              <Group gap="md">
                <div style={{ flex: 1 }}>
                  <Text size="sm" fw={600} c="dimmed" mb="xs">
                    Common Name (CN)
                  </Text>
                  <Text size="sm">{certificate.commonName}</Text>
                </div>
                <div style={{ flex: 1 }}>
                  <Text size="sm" fw={600} c="dimmed" mb="xs">
                    Organization (O)
                  </Text>
                  <Text size="sm">{certificate.subject?.organization || '-'}</Text>
                </div>
              </Group>

              <Group gap="md">
                <div style={{ flex: 1 }}>
                  <Text size="sm" fw={600} c="dimmed" mb="xs">
                    Organizational Unit (OU)
                  </Text>
                  <Text size="sm">{certificate.subject?.unit || '-'}</Text>
                </div>
                <div style={{ flex: 1 }}>
                  <Text size="sm" fw={600} c="dimmed" mb="xs">
                    Country (C)
                  </Text>
                  <Text size="sm">{certificate.subject?.country || '-'}</Text>
                </div>
              </Group>

              <Group gap="md">
                <div style={{ flex: 1 }}>
                  <Text size="sm" fw={600} c="dimmed" mb="xs">
                    State (ST)
                  </Text>
                  <Text size="sm">{certificate.subject?.state || '-'}</Text>
                </div>
                <div style={{ flex: 1 }}>
                  <Text size="sm" fw={600} c="dimmed" mb="xs">
                    Locality (L)
                  </Text>
                  <Text size="sm">{certificate.subject?.locality || '-'}</Text>
                </div>
              </Group>

              {certificate.subject?.altNames && certificate.subject.altNames.length > 0 && (
                <div>
                  <Text size="sm" fw={600} c="dimmed" mb="xs">
                    Alternative Names
                  </Text>
                  <Stack gap="xs">
                    {certificate.subject.altNames.map((name, idx) => (
                      <Text key={idx} size="sm">
                        • {name}
                      </Text>
                    ))}
                  </Stack>
                </div>
              )}
            </Stack>
          </Card>
        </Tabs.Panel>

        {/* Issuer Tab */}
        <Tabs.Panel value="issuer" pt="md">
          <Card withBorder className="info-card">
            <Stack gap="md">
              <Group gap="md">
                <div style={{ flex: 1 }}>
                  <Text size="sm" fw={600} c="dimmed" mb="xs">
                    Issuer
                  </Text>
                  <Text size="sm">{certificate.issuer}</Text>
                </div>
              </Group>

              {certificate.issuerDetails && (
                <>
                  <Group gap="md">
                    <div style={{ flex: 1 }}>
                      <Text size="sm" fw={600} c="dimmed" mb="xs">
                        Organization (O)
                      </Text>
                      <Text size="sm">{certificate.issuerDetails?.organization || '-'}</Text>
                    </div>
                    <div style={{ flex: 1 }}>
                      <Text size="sm" fw={600} c="dimmed" mb="xs">
                        Country (C)
                      </Text>
                      <Text size="sm">{certificate.issuerDetails?.country || '-'}</Text>
                    </div>
                  </Group>

                  <Group gap="md">
                    <div style={{ flex: 1 }}>
                      <Text size="sm" fw={600} c="dimmed" mb="xs">
                        Common Name (CN)
                      </Text>
                      <Text size="sm">{certificate.issuerDetails?.commonName || '-'}</Text>
                    </div>
                  </Group>
                </>
              )}
            </Stack>
          </Card>
        </Tabs.Panel>

        {/* Validity Tab */}
        <Tabs.Panel value="validity" pt="md">
          <Card withBorder className="info-card">
            <Stack gap="md">
              <Group gap="md">
                <div style={{ flex: 1 }}>
                  <Group gap="xs" mb="xs">
                    <Calendar size={16} color="#888" />
                    <Text size="sm" fw={600} c="dimmed">
                      Issued On
                    </Text>
                  </Group>
                  <Text size="sm">{formatDate(certificate.issuedDate)}</Text>
                </div>
                <div style={{ flex: 1 }}>
                  <Group gap="xs" mb="xs">
                    <Calendar size={16} color="#888" />
                    <Text size="sm" fw={600} c="dimmed">
                      Expires On
                    </Text>
                  </Group>
                  <Text size="sm">{formatDate(certificate.expiryDate)}</Text>
                </div>
              </Group>

              <Divider />

              <div>
                <Text size="sm" fw={600} c="dimmed" mb="xs">
                  Validity Period
                </Text>
                <Text size="sm">
                  {Math.floor((new Date(certificate.expiryDate) - new Date(certificate.issuedDate)) / (1000 * 60 * 60 * 24))} days
                </Text>
              </div>

              <div>
                <Text size="sm" fw={600} c="dimmed" mb="xs">
                  Days Remaining
                </Text>
                <Text size="sm">
                  {Math.max(0, Math.ceil((new Date(certificate.expiryDate) - new Date()) / (1000 * 60 * 60 * 24)))} days
                </Text>
              </div>
            </Stack>
          </Card>
        </Tabs.Panel>

        {/* Extensions Tab */}
        <Tabs.Panel value="extensions" pt="md">
          <Card withBorder className="info-card">
            <Stack gap="md">
              {certificate.extensions && certificate.extensions.length > 0 ? (
                certificate.extensions.map((ext, idx) => (
                  <Box key={idx} p="sm" style={{ border: '1px solid #333', borderRadius: '4px' }}>
                    <Group justify="space-between" mb="xs">
                      <Text size="sm" fw={600}>
                        {ext.name}
                      </Text>
                      {ext.critical && (
                        <Badge size="sm" color="red" variant="light">
                          Critical
                        </Badge>
                      )}
                    </Group>
                    <Text size="sm" c="dimmed">
                      {ext.value}
                    </Text>
                  </Box>
                ))
              ) : (
                <Text c="dimmed">No extensions found</Text>
              )}
            </Stack>
          </Card>
        </Tabs.Panel>

        {/* PEM Tab */}
        <Tabs.Panel value="pem" pt="md">
          <Card withBorder className="pem-card">
            <Stack gap="md">
              <Group justify="space-between">
                <Text size="sm" fw={600}>
                  Certificate (PEM Format)
                </Text>
                <CopyButton value={certificate.pem} timeout={2000}>
                  {({ copied }) => (
                    <Tooltip label={copied ? 'Copied to clipboard' : 'Copy PEM'} withArrow position="left">
                      <ActionIcon color={copied ? 'green' : 'gray'} variant="subtle">
                        {copied ? <Check size={16} /> : <Copy size={16} />}
                      </ActionIcon>
                    </Tooltip>
                  )}
                </CopyButton>
              </Group>

              <Textarea
                value={certificate.pem}
                readOnly
                minRows={20}
                maxRows={30}
                className="pem-textarea"
              />

              <Button
                leftSection={<Download size={16} />}
                onClick={handleDownload}
                fullWidth
              >
                Download PEM
              </Button>
            </Stack>
          </Card>
        </Tabs.Panel>
      </Tabs>
    </Container>
  );
};

export default CertificateDetailPage;
