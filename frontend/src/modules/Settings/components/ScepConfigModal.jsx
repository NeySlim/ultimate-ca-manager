import React from 'react';
import { TextInput, PasswordInput, Switch, Button, Group, Stack, Select } from '@mantine/core';

const ScepConfigModal = ({ context, id, innerProps }) => {
  return (
    <Stack spacing="md">
      <TextInput 
        label="SCEP Server URL" 
        placeholder="http://scep.example.com/scep/pkiclient.exe"
        defaultValue={innerProps.url || ''}
        data-autofocus 
      />
      
      <TextInput 
        label="CA Identifier" 
        placeholder="The CA instance name"
      />

      <Group grow>
        <Select
          label="Hash Algorithm"
          data={['SHA-1 (Legacy)', 'SHA-256', 'SHA-512']}
          defaultValue="SHA-256"
        />
        <Select
          label="Encryption"
          data={['DES3 (Legacy)', 'AES-128', 'AES-256']}
          defaultValue="AES-128"
        />
      </Group>

      <PasswordInput
        label="Challenge Password"
        placeholder="Shared secret if required"
      />

      <Switch 
        label="Enable Dynamic Challenge" 
        description="Generate unique password per request"
      />

      <Group position="right" mt="md">
        <Button variant="default" onClick={() => context.closeModal(id)}>
          Cancel
        </Button>
        <Button onClick={() => context.closeModal(id)}>
          Save Configuration
        </Button>
      </Group>
    </Stack>
  );
};

export default ScepConfigModal;
