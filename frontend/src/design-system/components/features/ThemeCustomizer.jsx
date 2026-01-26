import { useState } from 'react';
import styles from './ThemeCustomizer.module.css';
import { Card } from '../primitives/Card';
import { Button } from '../primitives/Button';
import { Badge } from '../primitives/Badge';
import { Stack } from '../layout/Stack';
import { Grid } from '../layout/Grid';
import { Palette, Download, Upload, ArrowsClockwise, Check } from '@phosphor-icons/react';

const THEME_PRESETS = [
  { id: 'ocean', name: 'Ocean', description: 'Cool blues', colors: { primary: '#3b82f6', secondary: '#06b6d4', accent: '#0ea5e9' }, gradient: 'linear-gradient(135deg, #3b82f6 0%, #06b6d4 100%)' },
  { id: 'forest', name: 'Forest', description: 'Natural greens', colors: { primary: '#22c55e', secondary: '#10b981', accent: '#84cc16' }, gradient: 'linear-gradient(135deg, #22c55e 0%, #10b981 100%)' },
  { id: 'sunset', name: 'Sunset', description: 'Warm oranges', colors: { primary: '#f97316', secondary: '#ec4899', accent: '#f59e0b' }, gradient: 'linear-gradient(135deg, #f97316 0%, #ec4899 100%)' },
  { id: 'lavender', name: 'Lavender', description: 'Soft purples', colors: { primary: '#a855f7', secondary: '#8b5cf6', accent: '#c084fc' }, gradient: 'linear-gradient(135deg, #a855f7 0%, #8b5cf6 100%)' },
  { id: 'midnight', name: 'Midnight', description: 'Deep blues', colors: { primary: '#3730a3', secondary: '#1e40af', accent: '#4f46e5' }, gradient: 'linear-gradient(135deg, #3730a3 0%, #1e40af 100%)' },
  { id: 'cherry', name: 'Cherry', description: 'Bold reds', colors: { primary: '#ef4444', secondary: '#f43f5e', accent: '#dc2626' }, gradient: 'linear-gradient(135deg, #ef4444 0%, #f43f5e 100%)' },
];

export function ThemeCustomizer() {
  const [selectedPreset, setSelectedPreset] = useState('ocean');
  const [customColors, setCustomColors] = useState({ primary: '#3b82f6', secondary: '#06b6d4', accent: '#0ea5e9' });

  const applyTheme = (colors) => {
    const root = document.documentElement;
    root.style.setProperty('--color-primary-500', colors.primary);
    root.style.setProperty('--color-secondary-500', colors.secondary);
    root.style.setProperty('--color-accent-500', colors.accent);
    localStorage.setItem('ucm-theme', JSON.stringify(colors));
  };

  const handlePresetClick = (preset) => {
    setSelectedPreset(preset.id);
    setCustomColors(preset.colors);
    applyTheme(preset.colors);
  };

  const handleColorChange = (colorKey, value) => {
    const newColors = { ...customColors, [colorKey]: value };
    setCustomColors(newColors);
    applyTheme(newColors);
    setSelectedPreset(null);
  };

  const handleExport = () => {
    const blob = new Blob([JSON.stringify({ colors: customColors, preset: selectedPreset }, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ucm-theme-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleImport = () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = (e) => {
      const file = e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (event) => {
        try {
          const data = JSON.parse(event.target.result);
          if (data.colors) {
            setCustomColors(data.colors);
            applyTheme(data.colors);
            if (data.preset) setSelectedPreset(data.preset);
          }
        } catch (err) { console.error(err); }
      };
      reader.readAsText(file);
    };
    input.click();
  };

  const handleReset = () => {
    const defaultTheme = THEME_PRESETS[0];
    setSelectedPreset(defaultTheme.id);
    setCustomColors(defaultTheme.colors);
    applyTheme(defaultTheme.colors);
  };

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div className={styles.headerIcon}><Palette size={24} weight="duotone" /></div>
        <div>
          <h3 className={styles.title}>Theme Customization</h3>
          <p className={styles.subtitle}>Personalize your interface</p>
        </div>
      </div>
      <Stack spacing="lg">
        <div>
          <h4 className={styles.sectionTitle}>Presets</h4>
          <Grid columns={3} gap="md">
            {THEME_PRESETS.map((preset) => (
              <Card key={preset.id} className={`${styles.presetCard} ${selectedPreset === preset.id ? styles.selected : ''}`} onClick={() => handlePresetClick(preset)}>
                <div className={styles.presetGradient} style={{ background: preset.gradient }} />
                <div className={styles.presetContent}>
                  <div className={styles.presetName}>{preset.name} {selectedPreset === preset.id && <Check size={16} weight="bold" />}</div>
                  <div className={styles.presetDescription}>{preset.description}</div>
                </div>
              </Card>
            ))}
          </Grid>
        </div>
        <div>
          <h4 className={styles.sectionTitle}>Custom Colors</h4>
          <Grid columns={3} gap="md">
            {['primary', 'secondary', 'accent'].map((key) => (
              <div key={key} className={styles.colorPicker}>
                <label className={styles.colorLabel}>{key.charAt(0).toUpperCase() + key.slice(1)}</label>
                <div className={styles.colorInputWrapper}>
                  <input type="color" value={customColors[key]} onChange={(e) => handleColorChange(key, e.target.value)} className={styles.colorInput} />
                  <span className={styles.colorValue}>{customColors[key]}</span>
                </div>
              </div>
            ))}
          </Grid>
        </div>
        <div className={styles.actions}>
          <Button variant="secondary" size="sm" onClick={handleExport}><Download size={16} /> Export</Button>
          <Button variant="secondary" size="sm" onClick={handleImport}><Upload size={16} /> Import</Button>
          <Button variant="ghost" size="sm" onClick={handleReset}><ArrowsClockwise size={16} /> Reset</Button>
        </div>
      </Stack>
    </div>
  );
}
