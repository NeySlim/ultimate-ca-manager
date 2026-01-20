import React from 'react';
import { TextInput, PasswordInput, Switch, Button, Group, Stack, Select, Alert } from '@mantine/core';
import { Info } from '@phosphor-icons/react';

const ScepConfigModal = ({ context, id, innerProps }) => {
  return (
    <Stack spacing="md">
      <Alert icon={<Info size={16} />} title="SCEP Server Configuration" color="blue">
        Configure the built-in SCEP server behavior.
      </Alert>

      <Switch 
        label="Auto-Approve Requests" 
        description="Automatically issue certificates for valid SCEP requests without manual approval."
        defaultChecked={true} 
      />
      
      <PasswordInput
        label="Global Challenge Password"
        placeholder="Shared secret required for all requests (Optional)"
        description="If set, clients must provide this password in the enrollment request."
      />

      <Select
        label="Signer Certificate Validity"
        description="Validity period for issued certificates"
        data={['30 Days', '90 Days', '1 Year', '2 Years']}
        defaultValue="1 Year"
      />

      <Group position="right" mt="md">
        <Button variant="default" onClick={() => context.closeModal(id)}>
          Cancel
        </Button>
        <Button onClick={() => {
            // Mock save logic
            alert("Configuration saved");
            context.closeModal(id);
        }}>
          Save Configuration
        </Button>
      </Group>
    </Stack>
  );
};

export default ScepConfigModal;
