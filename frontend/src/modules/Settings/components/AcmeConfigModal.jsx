import React from 'react';
import { Input, NumberInput, Switch, Button, Group, Stack, Select } from '@mantine/core';

const AcmeConfigModal = ({ context, id, innerProps }) => {
  return (
    <Stack spacing="md">
      <Input 
        label="ACME Directory URL" 
        placeholder="https://acme-v02.api.letsencrypt.org/directory"
        defaultValue={innerProps.url || ''}
        data-autofocus 
      />
      
      <Group grow>
        <Select
          label="Challenge Type"
          data={['HTTP-01', 'DNS-01', 'TLS-ALPN-01']}
          defaultValue="HTTP-01"
        />
        <NumberInput 
          label="Renewal Days" 
          description="Renew before expiry"
          defaultValue={30} 
          min={1}
        />
      </Group>

      <Switch 
        label="Enable External Account Binding (EAB)" 
        description="Required for some ACME providers like ZeroSSL"
      />

      <Stack spacing="xs" style={{ border: '1px solid var(--border-primary)', padding: 'var(--spacing-md)', borderRadius: 'var(--radius)', background: 'var(--bg-tertiary)' }}>
        <Input label="EAB Key ID" placeholder="Key ID" disabled />
        <Input label="EAB HMAC Key" placeholder="HMAC Key" disabled />
      </Stack>

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

export default AcmeConfigModal;
