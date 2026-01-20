import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  Input, Select, MultiSelect, Code, Group, Text, Paper
} from '@mantine/core';
import { CreationWizard, WizardStep } from '../../../components/ui/Wizards/CreationWizard';
import { CsrService } from '../services/csr.service';
import { notifications } from '../../../components/ui/notifications';

const CSRCreatePage = () => {
  const navigate = useNavigate();
  const [activeStep, setActiveStep] = useState(0);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const [formData, setFormData] = useState({
    cn: '',
    department: '',
    key_type: 'RSA 2048',
    sans: []
  });

  const handleChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const handleSubmit = async () => {
    setLoading(true);
    try {
      const response = await CsrService.create(formData);
      setResult(response);
      notifications.show({
        title: 'Success',
        message: 'CSR Created Successfully',
        color: 'green'
      });
      setActiveStep(prev => prev + 1);
    } catch (error) {
      notifications.show({
        title: 'Error',
        message: error.message || 'Failed to create CSR',
        color: 'red'
      });
    } finally {
      setLoading(false);
    }
  };

  const steps = [
    {
      label: 'Details',
      description: 'Subject Information',
      content: (
        <WizardStep>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', maxWidth: '400px', margin: '0 auto' }}>
            <Input
              label="Common Name (CN)"
              placeholder="e.g. web.internal.corp"
              required
              value={formData.cn}
              onChange={(e) => handleChange('cn', e.currentTarget.value)}
              size="xs"
            />
            <Input
              label="Department / Unit"
              placeholder="e.g. DevOps"
              value={formData.department}
              onChange={(e) => handleChange('department', e.currentTarget.value)}
              size="xs"
            />
            <Select
              label="Key Algorithm"
              data={['RSA 2048', 'RSA 4096', 'EC P-256', 'EC P-384']}
              value={formData.key_type}
              onChange={(val) => handleChange('key_type', val)}
              size="xs"
            />
            <MultiSelect
              label="Subject Alternative Names (SANs)"
              placeholder="Type and press Enter"
              data={[]}
              searchable
              creatable
              getCreateLabel={(query) => `+ Add ${query}`}
              onCreate={(query) => {
                const item = { value: query, label: query };
                handleChange('sans', [...formData.sans, query]);
                return item;
              }}
              value={formData.sans}
              onChange={(val) => handleChange('sans', val)}
              size="xs"
            />
          </div>
        </WizardStep>
      ),
      disabled: !formData.cn
    },
    {
      label: 'Review',
      description: 'Confirm details',
      content: (
        <WizardStep>
           <div style={{ maxWidth: '500px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <Text size="xs" c="dimmed">Please review the information before generating the request.</Text>
              
              <Paper p="sm" withBorder style={{ background: 'var(--bg-surface)', borderColor: 'var(--border-color)' }}>
                  <Group justify="space-between" mb={8}>
                      <Text size="xs" fw={500}>Common Name:</Text>
                      <Text size="xs">{formData.cn}</Text>
                  </Group>
                  <Group justify="space-between" mb={8}>
                      <Text size="xs" fw={500}>Department:</Text>
                      <Text size="xs">{formData.department || '-'}</Text>
                  </Group>
                  <Group justify="space-between" mb={8}>
                      <Text size="xs" fw={500}>Key Type:</Text>
                      <Text size="xs">{formData.key_type}</Text>
                  </Group>
                  <div style={{ marginTop: '8px' }}>
                      <Text size="xs" fw={500} mb={4}>SANs:</Text>
                      {formData.sans.length > 0 ? (
                          <Group gap="xs">
                              {formData.sans.map(san => (
                                  <Code key={san} fz="xs">{san}</Code>
                              ))}
                          </Group>
                      ) : (
                          <Text size="xs" c="dimmed">None</Text>
                      )}
                  </div>
              </Paper>
           </div>
        </WizardStep>
      )
    }
  ];

  if (result) {
    return (
      <CreationWizard
        title="Create New CSR"
        steps={[...steps, { label: 'Complete', description: 'Get your CSR' }]}
        activeStep={steps.length}
        onStepChange={() => {}}
        onCancel={() => navigate('/csrs')}
        onComplete={() => navigate('/csrs')}
      >
         <WizardStep>
           <div style={{ maxWidth: '600px', margin: '0 auto', textAlign: 'center' }}>
              <Text size="md" fw={700} mb="sm">CSR Generated Successfully</Text>
              <Text size="xs" c="dimmed" mb="lg">
                  Your request has been created. You can download the CSR file below.
              </Text>

              <Paper p="sm" withBorder style={{ textAlign: 'left', background: 'var(--bg-surface)', overflow: 'auto', borderColor: 'var(--border-color)', maxHeight: '300px' }}>
                  <Code block fz="xs">
                      {`-----BEGIN CERTIFICATE REQUEST-----
MIIB9TCCAZ4CAQAwGjEYMBYGA1UEAwwPd2ViLmRldi5sb2NhbCBVMQwKRGV2T3Bz
... (Mock CSR Data for ${formData.cn}) ...
-----END CERTIFICATE REQUEST-----`}
                  </Code>
              </Paper>
              
              <Group justify="center" mt="xl">
                  <Button variant="default" onClick={() => navigate('/csrs')} size="xs">Back to List</Button>
                  <Button size="xs">Download .csr</Button>
              </Group>
           </div>
         </WizardStep>
      </CreationWizard>
    );
  }

  return (
    <CreationWizard
      title="Create New CSR"
      steps={steps}
      activeStep={activeStep}
      onStepChange={setActiveStep}
      onCancel={() => navigate('/csrs')}
      onComplete={handleSubmit}
      loading={loading}
    >
      {steps[activeStep].content}
    </CreationWizard>
  );
};

export default CSRCreatePage;
