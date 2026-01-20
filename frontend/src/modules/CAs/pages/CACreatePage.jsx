import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Group,
  Input,
  Select,
  NumberInput,
  Paper,
  Text,
  Radio,
  Stack,
  Divider,
  Code
} from '@mantine/core';
import {
  CheckCircle,
} from '@phosphor-icons/react';
import { CreationWizard, WizardStep } from '../../../components/ui/Wizards/CreationWizard';
import { caService } from '../services/ca.service';
import './CACreatePage.css';

const CACreatePage = () => {
  const navigate = useNavigate();
  const [activeStep, setActiveStep] = useState(0);
  const [loading, setLoading] = useState(false);
  const [completed, setCompleted] = useState(false);

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

  const handleChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const handleSubmit = async () => {
    setLoading(true);
    try {
      await caService.createCA(formData);
      setCompleted(true);
      // We don't navigate immediately, let user see success screen
    } catch (error) {
      console.error("Failed to create CA", error);
    } finally {
      setLoading(false);
    }
  };

  const steps = [
    {
      label: 'Type',
      description: 'Root/Intermediate',
      content: (
        <WizardStep>
           <Stack mt="sm" gap="sm" style={{ maxWidth: '500px', margin: '0 auto' }}>
            <Text size="sm" fw={600} style={{ color: 'var(--text-primary)' }}>Select CA Type</Text>
            <Radio.Group 
              value={formData.type} 
              onChange={(val) => handleChange('type', val)}
            >
              <Stack gap="xs">
                <Paper p="sm" withBorder className={`radio-card ${formData.type === 'root' ? 'selected' : ''}`} style={{ background: 'var(--bg-surface)', borderColor: 'var(--border-color)' }}>
                  <Radio value="root" label="Root CA" size="xs" style={{marginBottom: 4}} />
                  <Text size="xs" c="dimmed" pl={24}>
                    Self-signed authority. The root of trust for your hierarchy.
                  </Text>
                </Paper>
                <Paper p="sm" withBorder className={`radio-card ${formData.type === 'intermediate' ? 'selected' : ''}`} style={{ background: 'var(--bg-surface)', borderColor: 'var(--border-color)' }}>
                  <Radio value="intermediate" label="Intermediate CA" size="xs" style={{marginBottom: 4}} />
                  <Text size="xs" c="dimmed" pl={24}>
                    Signed by another CA. Used for issuing certificates or other intermediates.
                  </Text>
                </Paper>
              </Stack>
            </Radio.Group>
          </Stack>
        </WizardStep>
      )
    },
    {
      label: 'Identity',
      description: 'Subject Info',
      content: (
        <WizardStep>
          <Stack mt="sm" gap="sm" style={{ maxWidth: '500px', margin: '0 auto' }}>
            <Text size="sm" fw={600}>CA Identity</Text>
            <Input 
              label="Common Name (CN)" 
              placeholder="e.g. MyCorp Root CA G1" 
              value={formData.commonName}
              onChange={(e) => handleChange('commonName', e.target.value)}
              required
              size="xs"
            />
            <Input 
              label="Organization (O)" 
              placeholder="e.g. MyCorp Inc."
              value={formData.organization}
              onChange={(e) => handleChange('organization', e.target.value)}
              size="xs"
            />
            <Select
              label="Country (C)"
              placeholder="Select country"
              data={['US', 'FR', 'DE', 'UK', 'JP']}
              value={formData.country}
              onChange={(val) => handleChange('country', val)}
              size="xs"
            />
          </Stack>
        </WizardStep>
      )
    },
    {
      label: 'Security',
      description: 'Key & Algo',
      content: (
        <WizardStep>
          <Stack mt="sm" gap="sm" style={{ maxWidth: '500px', margin: '0 auto' }}>
            <Text size="sm" fw={600}>Key Configuration</Text>
            <Select
              label="Key Algorithm"
              data={['RSA', 'ECDSA']}
              value={formData.keyAlgo}
              onChange={(val) => handleChange('keyAlgo', val)}
              size="xs"
            />
            {formData.keyAlgo === 'RSA' ? (
              <Select
                label="Key Size"
                data={['2048', '4096', '8192']}
                value={formData.keySize}
                onChange={(val) => handleChange('keySize', val)}
                size="xs"
              />
            ) : (
              <Select
                label="Curve"
                data={['P-256', 'P-384', 'P-521']}
                value={formData.keySize}
                onChange={(val) => handleChange('keySize', val)}
                size="xs"
              />
            )}
            <NumberInput
              label="Validity Period (Years)"
              value={formData.validityYears}
              onChange={(val) => handleChange('validityYears', val)}
              min={1}
              max={20}
              size="xs"
            />
          </Stack>
        </WizardStep>
      )
    },
    {
      label: 'Review',
      description: 'Confirm',
      content: (
        <WizardStep>
          <Stack mt="sm" gap="sm" style={{ maxWidth: '500px', margin: '0 auto' }}>
            <Text size="sm" fw={600}>Review Configuration</Text>
            <Paper p="sm" withBorder style={{ background: 'var(--bg-surface)', borderColor: 'var(--border-color)' }}>
                <Stack gap="xs">
                    <Group justify="space-between">
                        <Text size="xs" c="dimmed">Type</Text>
                        <Text size="xs" fw={500}>{formData.type.toUpperCase()}</Text>
                    </Group>
                    <Divider color="var(--border-color)" />
                    <Group justify="space-between">
                        <Text size="xs" c="dimmed">Common Name</Text>
                        <Text size="xs" fw={500}>{formData.commonName}</Text>
                    </Group>
                    <Group justify="space-between">
                        <Text size="xs" c="dimmed">Organization</Text>
                        <Text size="xs">{formData.organization}</Text>
                    </Group>
                    <Divider color="var(--border-color)" />
                    <Group justify="space-between">
                        <Text size="xs" c="dimmed">Key Spec</Text>
                        <Text size="xs" style={{ fontFamily: 'var(--font-mono)' }}>{formData.keyAlgo} - {formData.keySize}</Text>
                    </Group>
                    <Group justify="space-between">
                        <Text size="xs" c="dimmed">Validity</Text>
                        <Text size="xs">{formData.validityYears} Years</Text>
                    </Group>
                </Stack>
            </Paper>
          </Stack>
        </WizardStep>
      )
    }
  ];

  if (completed) {
      return (
        <CreationWizard
            title="Create New CA"
            steps={[...steps, { label: 'Complete', description: 'Finished' }]}
            activeStep={steps.length}
            onStepChange={() => {}}
            onCancel={() => navigate('/cas/tree')}
            onComplete={() => navigate('/cas/tree')}
        >
            <WizardStep>
              <Stack mt="xl" align="center" gap="md">
                <CheckCircle size={48} color="var(--accent-primary)" weight="fill" className="icon-gradient-glow" />
                <Text size="lg" fw={600}>Success</Text>
                <Text size="sm" c="dimmed" ta="center" style={{ maxWidth: '400px' }}>
                    The Certificate Authority has been initialized successfully.
                </Text>
                <Group mt="md">
                    <Text size="xs" c="dimmed">Please backup your root keys securely.</Text>
                </Group>
              </Stack>
            </WizardStep>
        </CreationWizard>
      )
  }

  return (
    <CreationWizard
      title="Create New CA"
      steps={steps}
      activeStep={activeStep}
      onStepChange={setActiveStep}
      onCancel={() => navigate('/cas/tree')}
      onComplete={handleSubmit}
      loading={loading}
    >
      {steps[activeStep].content}
    </CreationWizard>
  );
};

export default CACreatePage;
