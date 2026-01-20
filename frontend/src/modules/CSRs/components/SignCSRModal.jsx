import React, { useState } from 'react';
import {
  Button,
  Group,
  Select,
  NumberInput,
  Stack,
  Text,
  Alert,
} from '@mantine/core';
import { WarningCircle, PenNib } from '@phosphor-icons/react';

const SignCSRModal = ({ csr, onSign, onCancel }) => {
  const [selectedCA, setSelectedCA] = useState('');
  const [validityDays, setValidityDays] = useState(365);
  const [loading, setLoading] = useState(false);

  const handleSubmit = () => {
    if (!selectedCA) return;
    setLoading(true);
    // Simulate API
    setTimeout(() => {
        setLoading(false);
        onSign({ ca: selectedCA, validity: validityDays });
    }, 1500);
  };

  return (
    <Stack gap="md">
      <Alert variant="light" color="blue" title="CSR Signing">
        You are about to sign the request for <strong>{csr.commonName}</strong>.
      </Alert>

      <Select
        label="Signing Authority (Issuer)"
        placeholder="Select CA"
        data={['Root CA - UCM Global', 'Intermediate CA - Web Server']}
        value={selectedCA}
        onChange={setSelectedCA}
        required
      />

      <NumberInput
        label="Validity Period (Days)"
        value={validityDays}
        onChange={setValidityDays}
        min={1}
        max={3650}
      />

      <Alert variant="light" color="yellow" icon={<WarningCircle size={16} />}>
        Ensure you have verified the identity of the requester before signing.
      </Alert>

      <Group justify="flex-end" mt="md">
        <Button variant="default" onClick={onCancel} disabled={loading}>
          Cancel
        </Button>
        <Button 
            onClick={handleSubmit} 
            loading={loading} 
            disabled={!selectedCA}
            leftSection={<PenNib size={16} />}
        >
          Sign Certificate
        </Button>
      </Group>
    </Stack>
  );
};

export default SignCSRModal;
