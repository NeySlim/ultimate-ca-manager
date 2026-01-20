import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Button,
  Badge,
  Text,
  Group
} from '../../../components/ui';
import { ArrowLeft, User, CheckCircle, XCircle } from '@phosphor-icons/react';
import { PageHeader } from '../../../components/ui/Layout';
import ResizableTable from '../../../components/ui/Layout/ResizableTable';
import { AcmeService } from '../services/acme.service';

const ACMEAccounts = () => {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const data = await AcmeService.getAccounts();
      setItems(data);
    } catch (error) {
      console.error("Failed to fetch ACME accounts", error);
    } finally {
      setLoading(false);
    }
  };

  const columns = [
    {
      key: 'account_id',
      label: 'Account ID',
      width: 250,
      render: (row) => (
        <Group gap="xs" wrap="nowrap">
          <User size={16} className="icon-gradient-subtle" />
          <Text size="sm" fw={500} style={{ fontFamily: 'var(--font-mono)' }}>{row.account_id.substring(0, 16)}...</Text>
        </Group>
      )
    },
    {
      key: 'status',
      label: 'Status',
      width: 100,
      render: (row) => (
        <Badge 
          color={row.status === 'valid' ? 'green' : 'gray'} 
          variant="dot" 
          size="sm"
        >
          {row.status}
        </Badge>
      )
    },
    {
      key: 'contact',
      label: 'Contact',
      flex: true,
      render: (row) => (
        <Text size="sm" c="dimmed">
          {Array.isArray(row.contact) ? row.contact.join(', ').replace(/mailto:/g, '') : '-'}
        </Text>
      )
    },
    {
      key: 'created_at',
      label: 'Created',
      width: 150,
      render: (row) => (
        <Text size="sm">{new Date(row.created_at).toLocaleDateString()}</Text>
      )
    }
  ];

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <PageHeader 
        title="ACME Accounts" 
        backAction={() => navigate('/acme')}
      />

      <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
         <ResizableTable 
            columns={columns}
            data={items}
            emptyMessage="No ACME accounts found"
         />
      </div>
    </div>
  );
};

export default ACMEAccounts;
