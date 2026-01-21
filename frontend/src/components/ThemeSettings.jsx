import React from 'react';
import { Modal, Button, Stack, Text, SegmentedControl, SimpleGrid } from './ui';
import { useTheme } from '../contexts/ThemeContext';
import { colorPalettes } from '../theme/colors';

export const ThemeSettings = ({ opened, onClose }) => {
  const { palette, setPalette, colorScheme, setColorScheme, density, setDensity } = useTheme();

  return (
    <Modal opened={opened} onClose={onClose} title="Display Settings" size="lg">
      <Stack gap="xl">
        {/* Mode light/dark */}
        <div>
          <Text fw={600} mb="sm">Display Mode</Text>
          <SegmentedControl
            fullWidth
            value={colorScheme}
            onChange={(value) => setColorScheme(value)}
            data={[
              { label: '🌙 Dark', value: 'dark' },
              { label: '☀️ Light', value: 'light' },
            ]}
          />
        </div>

        {/* Density */}
        <div>
          <Text fw={600} mb="sm">Density</Text>
          <SegmentedControl
            fullWidth
            value={density}
            onChange={(value) => setDensity(value)}
            data={[
              { label: '📏 Compact', value: 'compact' },
              { label: '📐 Normal', value: 'normal' },
              { label: '📊 Comfortable', value: 'comfortable' },
            ]}
          />
        </div>

        {/* Colors */}
        <div>
          <Text fw={600} mb="sm">❄️ Cold Tones</Text>
          <SimpleGrid cols={3} spacing="xs">
            {Object.entries(colorPalettes)
              .filter(([_, p]) => p.category === 'cold')
              .map(([key, p]) => (
                <Button
                  key={key}
                  variant={palette === key ? 'filled' : 'outline'}
                  onClick={() => setPalette(key)}
                  style={{ 
                    backgroundColor: palette === key ? p.primary : undefined,
                    borderColor: p.primary,
                    color: palette === key ? '#fff' : p.primary
                  }}
                >
                  {p.name}
                </Button>
              ))}
          </SimpleGrid>
        </div>

        <div>
          <Text fw={600} mb="sm">🔥 Warm Tones</Text>
          <SimpleGrid cols={3} spacing="xs">
            {Object.entries(colorPalettes)
              .filter(([_, p]) => p.category === 'warm')
              .map(([key, p]) => (
                <Button
                  key={key}
                  variant={palette === key ? 'filled' : 'outline'}
                  onClick={() => setPalette(key)}
                  style={{ 
                    backgroundColor: palette === key ? p.primary : undefined,
                    borderColor: p.primary,
                    color: palette === key ? '#fff' : p.primary
                  }}
                >
                  {p.name}
                </Button>
              ))}
          </SimpleGrid>
        </div>
      </Stack>
    </Modal>
  );
};
