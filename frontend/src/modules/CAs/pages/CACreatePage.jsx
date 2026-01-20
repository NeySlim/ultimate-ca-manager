import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Button,
  Group,
  Stepper,
  TextInput,
  Select,
  NumberInput,
  Paper,
  Text,
  Radio,
  Stack,
  Divider,
} from '@mantine/core';
import {
  ShieldCheck,
  Certificate,
  Key,
  CalendarCheck,
  CheckCircle,
  CaretRight,
  CaretLeft,
} from '@phosphor-icons/react';
import { PageHeader, Grid, Widget } from '../../../components/ui/Layout';
import './CACreatePage.css';

const CACreatePage = () => {
  const navigate = useNavigate();
  const [active, setActive] = useState(0);
  const [loading, setLoading] = useState(false);

  // Form State
  const [formData, setFormData] = useState({
    type: 'root',
    commonName: '',
    organization: '',
    country: 'US',
    keyAlgo: 'RSA',
    keySize: '4096',
    validityYears: 10,
  });

  const nextStep = () => setActive((current) => (current < 4 ? current + 1 : current));
  const prevStep = () => setActive((current) => (current > 0 ? current - 1 : current));

  const handleChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const handleSubmit = () => {
    setLoading(true);
    // Simulate API call
    setTimeout(() => {
      setLoading(false);
      navigate('/cas/tree');
    }, 1500);
  };

  return (
    <div className="ca-create-page" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <PageHeader 
        title="Create New Certificate Authority" 
        backAction={() => navigate('/cas/tree')}
      />

      <Grid style={{ flex: 1, padding: '16px', overflowY: 'auto' }}>
        <Widget className="wizard-widget col-12" style={{ maxWidth: '1400px', margin: '0 auto', height: 'fit-content' }}>
          <Stepper active={active} onStepClick={setActive} color="blue" size="sm">
            
            {/* Step 1: CA Type */}
            <Stepper.Step label="Type" description="Root or Intermediate" icon={<ShieldCheck size={18} />}>
              <Stack mt="xl" gap="md">
                <Text size="lg" fw={600}>Select CA Type</Text>
                <Radio.Group 
                  value={formData.type} 
                  onChange={(val) => handleChange('type', val)}
                >
                  <Stack gap="sm">
                    <Paper p="md" withBorder className={`radio-card ${formData.type === 'root' ? 'selected' : ''}`}>
                      <Radio value="root" label="Root CA" style={{marginBottom: 8}} />
                      <Text size="sm" c="dimmed" pl={28}>
                        Self-signed authority. The root of trust for your hierarchy.
                      </Text>
                    </Paper>
                    <Paper p="md" withBorder className={`radio-card ${formData.type === 'intermediate' ? 'selected' : ''}`}>
                      <Radio value="intermediate" label="Intermediate CA" style={{marginBottom: 8}} />
                      <Text size="sm" c="dimmed" pl={28}>
                        Signed by another CA. Used for issuing certificates or other intermediates.
                      </Text>
                    </Paper>
                  </Stack>
                </Radio.Group>
              </Stack>
            </Stepper.Step>

            {/* Step 2: Identity */}
            <Stepper.Step label="Identity" description="Subject Info" icon={<Certificate size={18} />}>
              <Stack mt="xl" gap="md">
                <Text size="lg" fw={600}>CA Identity</Text>
                <TextInput 
                  label="Common Name (CN)" 
                  placeholder="e.g. MyCorp Root CA G1" 
                  value={formData.commonName}
                  onChange={(e) => handleChange('commonName', e.target.value)}
                  required
                />
                <TextInput 
                  label="Organization (O)" 
                  placeholder="e.g. MyCorp Inc."
                  value={formData.organization}
                  onChange={(e) => handleChange('organization', e.target.value)}
                />
                <Select
                  label="Country (C)"
                  placeholder="Select country"
                  data={['US', 'FR', 'DE', 'UK', 'JP']}
                  value={formData.country}
                  onChange={(val) => handleChange('country', val)}
                />
              </Stack>
            </Stepper.Step>

            {/* Step 3: Key Material */}
            <Stepper.Step label="Security" description="Key & Algo" icon={<Key size={18} />}>
              <Stack mt="xl" gap="md">
                <Text size="lg" fw={600}>Key Configuration</Text>
                <Select
                  label="Key Algorithm"
                  data={['RSA', 'ECDSA']}
                  value={formData.keyAlgo}
                  onChange={(val) => handleChange('keyAlgo', val)}
                />
                {formData.keyAlgo === 'RSA' ? (
                  <Select
                    label="Key Size"
                    data={['2048', '4096', '8192']}
                    value={formData.keySize}
                    onChange={(val) => handleChange('keySize', val)}
                  />
                ) : (
                  <Select
                    label="Curve"
                    data={['P-256', 'P-384', 'P-521']}
                    value={formData.keySize}
                    onChange={(val) => handleChange('keySize', val)}
                  />
                )}
                <NumberInput
                  label="Validity Period (Years)"
                  value={formData.validityYears}
                  onChange={(val) => handleChange('validityYears', val)}
                  min={1}
                  max={20}
                />
              </Stack>
            </Stepper.Step>

            {/* Step 4: Review */}
            <Stepper.Step label="Review" description="Confirm" icon={<CheckCircle size={18} />}>
              <Stack mt="xl" gap="md">
                <Text size="lg" fw={600}>Review Configuration</Text>
                <Paper p="md" withBorder bg="#151515">
                    <Stack gap="xs">
                        <Group justify="space-between">
                            <Text size="sm" c="dimmed">Type</Text>
                            <Text size="sm" fw={500}>{formData.type.toUpperCase()}</Text>
                        </Group>
                        <Divider color="#333" />
                        <Group justify="space-between">
                            <Text size="sm" c="dimmed">Common Name</Text>
                            <Text size="sm" fw={500}>{formData.commonName}</Text>
                        </Group>
                        <Group justify="space-between">
                            <Text size="sm" c="dimmed">Organization</Text>
                            <Text size="sm">{formData.organization}</Text>
                        </Group>
                        <Divider color="#333" />
                        <Group justify="space-between">
                            <Text size="sm" c="dimmed">Key Spec</Text>
                            <Text size="sm" className="mono-text">{formData.keyAlgo} - {formData.keySize}</Text>
                        </Group>
                        <Group justify="space-between">
                            <Text size="sm" c="dimmed">Validity</Text>
                            <Text size="sm">{formData.validityYears} Years</Text>
                        </Group>
                    </Stack>
                </Paper>
              </Stack>
            </Stepper.Step>

            <Stepper.Completed>
              <Stack mt="xl" align="center" gap="md">
                <CheckCircle size={64} color="var(--accent-primary)" weight="fill" className="icon-gradient-glow" />
                <Text size="xl" fw={600}>Ready to Initialize</Text>
                <Text c="dimmed" ta="center">
                    This will generate the key pair and initialize the Certificate Authority.
                    This action cannot be undone.
                </Text>
              </Stack>
            </Stepper.Completed>
          </Stepper>

          <Group justify="center" mt="xl" gap="md">
            {active > 0 && (
                <Button variant="default" onClick={prevStep} leftSection={<CaretLeft size={16} />}>
                Back
                </Button>
            )}
            {active < 4 ? (
                <Button onClick={nextStep} rightSection={<CaretRight size={16} />}>
                Next Step
                </Button>
            ) : (
                <Button onClick={handleSubmit} loading={loading} color="green">
                Initialize CA
                </Button>
            )}
          </Group>
        </Widget>
      </Grid>
    </div>
  );
};

export default CACreatePage;
