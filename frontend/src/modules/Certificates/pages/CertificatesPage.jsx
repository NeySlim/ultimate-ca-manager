import React, { useState, useEffect } from 'react';
import { useView } from '../../../core/context/ViewContext';
import { useSelection } from '../../../core/context/SelectionContext';
import CertificateListView from '../components/CertificateListView';
import CertificateGridView from '../components/CertificateGridView';
import { CertificateService } from '../services/certificates.service';
import { Loader, Center } from '@mantine/core';

const CertificatesPage = () => {
  const { viewMode } = useView();
  const { selectedItem, setSelectedItem } = useSelection();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadData = async () => {
        setLoading(true);
        try {
            const data = await CertificateService.getAll();
            setItems(data);
            // Auto-select first item if nothing selected
            if (data.length > 0 && !selectedItem) {
                setSelectedItem(data[0]);
            }
        } catch (error) {
            console.error("Failed to load certificates", error);
        } finally {
            setLoading(false);
        }
    };
    loadData();
  }, []);

  const handleSelect = (item) => {
    // Enrich item for PreviewPanel
    const enrichedItem = {
        ...item,
        type: 'Certificate',
        title: item.commonName,
        subtitle: item.issuer,
        details: item // Full object for details
    };
    setSelectedItem(enrichedItem);
  };

  if (loading) {
      return (
          <Center style={{ height: '100%' }}>
              <Loader color="blue" type="bars" />
          </Center>
      );
  }

  const ViewComponent = viewMode === 'grid' ? CertificateGridView : CertificateListView;

  return (
    <ViewComponent 
      items={items} 
      selectedId={selectedItem?.id} 
      onSelect={handleSelect} 
    />
  );
};

export default CertificatesPage;
