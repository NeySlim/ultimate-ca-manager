import { colorPalettes } from './colors';
import { rem } from '@mantine/core';

export const createMantineTheme = (palette, density) => {
  const selectedPalette = colorPalettes[palette] || colorPalettes.teal;
  
  // Density spacing
  const spacing = {
    compact: { xs: 4, sm: 6, md: 8, lg: 12, xl: 16 },
    normal: { xs: 8, sm: 10, md: 12, lg: 16, xl: 20 },
    comfortable: { xs: 12, sm: 16, md: 20, lg: 24, xl: 32 },
  }[density];

  // Density font sizes
  const fontSizes = {
    compact: { xs: 10, sm: 11, md: 12, lg: 13, xl: 14 },
    normal: { xs: 11, sm: 12, md: 14, lg: 16, xl: 18 },
    comfortable: { xs: 12, sm: 14, md: 16, lg: 18, xl: 20 },
  }[density];

  // Border radius (compact = square, comfortable = rounded)
  const radius = {
    compact: { xs: 2, sm: 2, md: 3, lg: 4, xl: 6 },
    normal: { xs: 2, sm: 4, md: 6, lg: 8, xl: 10 },
    comfortable: { xs: 4, sm: 6, md: 8, lg: 10, xl: 12 },
  }[density];

  return {
    primaryColor: 'brand',
    colors: {
      brand: [
        selectedPalette.light,
        selectedPalette.primary,
        selectedPalette.primary,
        selectedPalette.primary,
        selectedPalette.primary,
        selectedPalette.primary,
        selectedPalette.hover,
        selectedPalette.hover,
        selectedPalette.dark,
        selectedPalette.dark,
      ],
    },
    spacing,
    fontSizes,
    radius,
    defaultRadius: radius.md,
    
    components: {
      Button: {
        styles: {
          root: {
            fontWeight: 500,
            border: '1px solid var(--border-color)',
            color: 'var(--text-primary)',
            backgroundColor: 'var(--bg-element)',
          },
        },
      },
      Table: {
        styles: {
          root: {
            fontSize: fontSizes.sm,
            color: 'var(--text-primary)',
            backgroundColor: 'var(--bg-panel)',
          },
          th: {
            color: 'var(--text-secondary)',
            backgroundColor: 'var(--bg-element)',
            borderBottom: '1px solid var(--border-color)',
          },
          td: {
            borderBottom: '1px solid var(--border-color)',
          },
          tr: {
            '&:hover': {
              backgroundColor: 'var(--bg-element-hover)',
            }
          }
        },
      },
      Card: {
        styles: {
          root: {
            borderRadius: radius.md,
            backgroundColor: 'var(--bg-panel)',
            border: '1px solid var(--border-color)',
            color: 'var(--text-primary)',
          },
        },
      },
      TextInput: {
        styles: {
          input: {
            backgroundColor: 'var(--bg-app)',
            borderColor: 'var(--border-color)',
            color: 'var(--text-primary)',
          }
        }
      },
      Select: {
        styles: {
          input: {
            backgroundColor: 'var(--bg-app)',
            borderColor: 'var(--border-color)',
            color: 'var(--text-primary)',
          },
          dropdown: {
            backgroundColor: 'var(--bg-panel)',
            borderColor: 'var(--border-color)',
          },
          option: {
            color: 'var(--text-primary)',
            '&:hover': {
              backgroundColor: 'var(--bg-element-hover)',
            }
          }
        }
      },
      Tabs: {
        styles: {
          tab: {
            color: 'var(--text-secondary)',
            '&[data-active]': {
              color: 'var(--text-primary)',
              borderColor: 'var(--accent-primary)',
            },
            '&:hover': {
              backgroundColor: 'var(--bg-element-hover)',
              color: 'var(--text-primary)',
            }
          },
          list: {
            borderColor: 'var(--border-color)',
          }
        }
      }
    },
  };
};
