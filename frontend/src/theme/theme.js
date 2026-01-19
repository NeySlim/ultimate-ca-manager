import { createTheme } from '@mantine/core';
import { colorPalettes, baseColors } from './colors';

// Get active palette from localStorage or default
const getActivePalette = () => {
  const saved = localStorage.getItem('ucm-color-palette');
  return saved && colorPalettes[saved] ? saved : 'blue-sky';
};

const activePalette = getActivePalette();
const palette = colorPalettes[activePalette];

export const ucmTheme = createTheme({
  colorScheme: 'dark',
  
  colors: {
    dark: [
      baseColors.dark.text.primary,    // 0
      baseColors.dark.text.secondary,  // 1
      baseColors.dark.text.tertiary,   // 2
      baseColors.dark.bg.hover,        // 3
      baseColors.dark.bg.card,         // 4
      baseColors.dark.bg.tertiary,     // 5
      baseColors.dark.bg.secondary,    // 6
      baseColors.dark.bg.primary,      // 7
      '#0f0f0f',                       // 8
      '#050505'                        // 9
    ],
    
    // Primary accent color (from active palette)
    primary: [
      palette.colors.light,
      palette.colors.light,
      palette.colors.main,
      palette.colors.main,
      palette.colors.main,
      palette.colors.dark,
      palette.colors.dark,
      palette.colors.dark,
      palette.colors.dark,
      palette.colors.dark
    ]
  },

  primaryColor: 'primary',
  
  fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, Segoe UI, system-ui, sans-serif',
  fontFamilyMonospace: 'JetBrains Mono, Consolas, Monaco, Courier New, monospace',
  
  headings: {
    fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, Segoe UI, system-ui, sans-serif',
    fontWeight: '600',
    sizes: {
      h1: { fontSize: '32px', lineHeight: '1.3' },
      h2: { fontSize: '24px', lineHeight: '1.35' },
      h3: { fontSize: '20px', lineHeight: '1.4' },
      h4: { fontSize: '18px', lineHeight: '1.45' },
      h5: { fontSize: '16px', lineHeight: '1.5' },
      h6: { fontSize: '14px', lineHeight: '1.5' }
    }
  },

  fontSizes: {
    xs: '11px',
    sm: '13px',
    md: '15px',
    lg: '17px',
    xl: '20px'
  },

  spacing: {
    xs: '4px',
    sm: '8px',
    md: '12px',
    lg: '16px',
    xl: '20px'
  },

  radius: {
    xs: '3px',
    sm: '3px',
    md: '3px',
    lg: '3px',
    xl: '3px'
  },

  shadows: {
    xs: '0 1px 3px rgba(0, 0, 0, 0.2)',
    sm: '0 2px 4px rgba(0, 0, 0, 0.25)',
    md: '0 4px 8px rgba(0, 0, 0, 0.3)',
    lg: '0 8px 16px rgba(0, 0, 0, 0.35)',
    xl: '0 12px 24px rgba(0, 0, 0, 0.4)'
  },

  components: {
    Button: {
      defaultProps: {
        size: 'sm'
      },
      styles: {
        root: {
          height: '26px',
          padding: '0 12px',
          fontSize: '13px',
          fontWeight: 500,
          borderRadius: '3px'
        }
      }
    },
    
    TextInput: {
      styles: {
        input: {
          height: '30px',
          fontSize: '13px',
          borderRadius: '3px',
          backgroundColor: baseColors.dark.bg.secondary,
          borderColor: baseColors.dark.border,
          color: baseColors.dark.text.primary,
          '&:focus': {
            borderColor: palette.colors.main
          }
        }
      }
    },

    Table: {
      styles: {
        root: {
          fontSize: '13px'
        },
        th: {
          padding: '8px 12px',
          fontWeight: 600,
          backgroundColor: baseColors.dark.bg.secondary,
          borderBottom: `1px solid ${baseColors.dark.border}`
        },
        td: {
          padding: '8px 12px',
          borderBottom: `1px solid ${baseColors.dark.border}`
        }
      }
    }
  }
});

export { colorPalettes, baseColors };
