import { createTheme, rem } from '@mantine/core';
import { colorPalettes } from './colors';

// Helper to generate 10 shades from a single color
const generateShades = (color) => [
  '#f0f4f8',
  '#dbe4ef',
  '#c0d0e3',
  '#a2bbd6',
  '#82a5c9',
  color,     // 5 (primary)
  '#4a7fb7',
  '#3b6aa3',
  '#2d568f',
  '#20427a'
];

export const createMantineTheme = (paletteKey, density) => {
  // IGNORE DENSITY PARAMETER -> FORCE STRICT COMPACT
  // The user explicitly wants "File Manager" aesthetic which is fixed 13px/26px
  
  const palette = colorPalettes[paletteKey] || colorPalettes.teal;

  return createTheme({
    primaryColor: 'brand',
    defaultRadius: 'xs', // STRICT: 3px
    fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
    fontFamilyMonospace: 'JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    
    // Explicit sizing to match Design System
    fontSizes: {
      xs: rem(11),
      sm: rem(13), // Standard UI text (13px)
      md: rem(14),
      lg: rem(16),
      xl: rem(20),
    },

    radius: {
      xs: rem(3), // The standard square-ish look
      sm: rem(4),
      md: rem(6),
      lg: rem(8),
      xl: rem(12),
    },
    
    colors: {
      brand: generateShades(palette.primary),
      dark: [
        '#C1C2C5',
        '#A6A7AB',
        '#909296',
        '#5C5F66',
        '#373A40',
        '#2C2E33',
        '#25262B',
        '#1A1B1E', // 7 (Standard Mantine Dark) -> We use #1a1a1a from design
        '#141517',
        '#101113',
      ],
    },
    
    components: {
      Button: {
        defaultProps: {
          size: 'sm',
          radius: 'xs',
        },
        styles: (theme, props, u) => ({
          root: {
            height: rem(26), // Strict 26px height
            padding: `0 ${rem(12)}`,
            fontSize: rem(13),
            fontWeight: 500,
            border: '1px solid transparent',
          },
        }),
        vars: (theme, props) => {
          if (props.variant === 'default' || props.variant === 'outline') {
            return {
              root: {
                '--button-bg': '#333333',
                '--button-hover': '#3a3a3a',
                '--button-color': '#e8e8e8',
                '--button-bd': '1px solid #444444',
              }
            };
          }
          return {};
        }
      },
      Badge: {
        defaultProps: {
          size: 'md',
          radius: 'xs',
        },
        styles: {
          root: {
            textTransform: 'uppercase',
            fontWeight: 600,
            fontSize: rem(11),
            letterSpacing: '0.5px',
            padding: `${rem(4)} ${rem(8)}`,
            height: 'auto',
            minHeight: rem(20),
          }
        }
      },
      TextInput: {
        defaultProps: {
          size: 'sm',
          radius: 'xs',
        },
        styles: {
          input: {
            backgroundColor: '#2a2a2a',
            borderColor: '#3a3a3a',
            color: '#e8e8e8',
            minHeight: rem(30),
            height: rem(30),
            fontSize: rem(13),
          }
        }
      },
      Select: {
        defaultProps: {
          size: 'sm',
          radius: 'xs',
        },
        styles: {
          input: {
            backgroundColor: '#2a2a2a',
            borderColor: '#3a3a3a',
            color: '#e8e8e8',
            minHeight: rem(30),
            height: rem(30),
            fontSize: rem(13),
          },
          dropdown: {
            backgroundColor: '#1e1e1e',
            borderColor: '#333',
          },
          option: {
            fontSize: rem(13),
            padding: '6px 10px',
            '&:hover': {
              backgroundColor: '#333',
            }
          }
        }
      },
      ActionIcon: {
        defaultProps: {
          size: 'sm',
          radius: 'xs',
        },
      },
      Modal: {
        defaultProps: {
          radius: 'md',
          overlayProps: {
            backgroundOpacity: 0.55,
            blur: 3,
          },
        },
        styles: {
          content: {
            backgroundColor: '#1e1e1e',
            border: '1px solid #333',
          },
          header: {
            backgroundColor: '#1e1e1e',
            borderBottom: '1px solid #333',
          }
        }
      },
      Stepper: {
        styles: {
          stepIcon: {
            borderRadius: '3px',
            borderWidth: '1px',
            backgroundColor: '#2a2a2a',
            borderColor: '#333',
            color: '#ccc'
          },
          separator: {
            backgroundColor: '#333',
            height: '1px'
          },
          stepLabel: {
            fontSize: '13px',
            color: '#e8e8e8'
          },
          stepDescription: {
             fontSize: '11px',
             color: '#888'
          }
        }
      }
    },
    
    other: {
      ...palette
    }
  });
};
