import React, { useState } from 'react';
import {
  Button,
  Group,
  Text,
  Badge,
  ActionIcon,
  Tooltip,
} from '@mantine/core';
import { useModals } from '@mantine/modals';
import {
  Gear,
  Globe,
  ShieldCheck,
  Database,
  Cloud,
  PenNib,
  Sliders,
  ToggleRight,
  ToggleLeft,
} from '@phosphor-icons/react';
import { PageHeader, Grid, Widget } from '../../../components/ui/Layout';
import ResizableTable from '../../../components/ui/Layout/ResizableTable';
import AcmeConfigModal from '../components/AcmeConfigModal';
import ScepConfigModal from '../components/ScepConfigModal';
import './SettingsPage.css';

// Mock Data
const MOCK_CONFIGS = [
  { id: 'acme', name: 'ACME Provider', type: 'Protocol', icon: Globe, status: 'Active', lastModified: '2024-03-20' },
  { id: 'scep', name: 'SCEP Server', type: 'Protocol', icon: ShieldCheck, status: 'Idle', lastModified: '2024-03-18' },
  { id: 'db', name: 'Database Connection', type: 'System', icon: Database, status: 'Connected', lastModified: '2024-03-15' },
  { id: 'backup', name: 'Cloud Backup', type: 'Storage', icon: Cloud, status: 'Daily', lastModified: '2024-03-10' },
];

const SettingsPage = () => {
  const modals = useModals();

  const handleConfigClick = (row) => {
    if (row.id === 'acme') {
        modals.openModal({
          title: 'ACME Protocol Configuration',
          centered: true,
          children: <AcmeConfigModal />,
        });
    } else if (row.id === 'scep') {
        modals.openModal({
            title: 'SCEP Protocol Configuration',
            centered: true,
            children: <ScepConfigModal />,
          });
    } else {
        console.log("Config not implemented:", row.id);
    }
  };

  const columns = [
    {
      key: 'name',
      label: 'Configuration Name',
      width: 250,
      render: (row) => (
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <row.icon size={18} className="icon-gradient-subtle" style={{ marginRight: 8 }} />
          <Text size="sm" fw={500}>{row.name}</Text>
        </div>
      )
    },
    {
      key: 'type',
      label: 'Category',
      width: 150,
      render: (row) => <Badge variant="outline" color="gray" size="xs">{row.type}</Badge>
    },
    {
      key: 'lastModified',
      label: 'Last Modified',
      width: 150,
      render: (row) => <Text size="sm" c="dimmed">{row.lastModified}</Text>
    },
    {
      key: 'status',
      label: 'Status',
      width: 100,
      render: (row) => (
        <Badge 
          color={row.status === 'Active' || row.status === 'Connected' ? 'green' : 'blue'} 
          variant="dot" 
          size="sm"
        >
          {row.status}
        </Badge>
      )
    },
    {
      key: 'actions',
      label: 'Actions',
      width: 120,
      render: (row) => (
        <Group gap={4}>
          <Tooltip label="Edit Configuration">
            <ActionIcon size="sm" variant="light" onClick={(e) => { e.stopPropagation(); handleConfigClick(row); }}>
              <Sliders size={16} />
            </ActionIcon>
          </Tooltip>
          <Tooltip label="Toggle">
             <ActionIcon size="sm" variant="subtle" color={row.status === 'Active' ? 'green' : 'gray'}>
                {row.status === 'Active' ? <ToggleRight size={24} weight="fill" /> : <ToggleLeft size={24} />}
             </ActionIcon>
          </Tooltip>
        </Group>
      )
    }
  ];

  return (
    <div className="settings-page" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <PageHeader 
        title="System Settings" 
        actions={
          <Button leftSection={<PenNib size={16} />} size="xs">
            Edit Global Config
          </Button>
        }
      />

      <Grid style={{ flex: 1, padding: '16px' }}>
        <Widget className="widget-full" style={{ height: '100%', padding: 0, overflow: 'hidden' }}>
          <ResizableTable 
            columns={columns}
            data={MOCK_CONFIGS}
            onRowClick={handleConfigClick}
          />
        </Widget>
      </Grid>
    </div>
  );
};

export default SettingsPage;
