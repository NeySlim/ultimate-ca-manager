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
        '#e8e8e8', // 0 - text-primary
        '#cccccc', // 1 - text-secondary
        '#888888', // 2 - text-tertiary  (dimmed uses this!)
        '#555555', // 3 - text-muted
        '#444444', // 4 - border-secondary
        '#333333', // 5 - border-primary
        '#2a2a2a', // 6 - bg-quaternary (hover)
        '#252525', // 7 - bg-tertiary (surface) - MANTINE DEFAULT
        '#1e1e1e', // 8 - bg-secondary (panel)
        '#1a1a1a', // 9 - bg-primary (app)
      ],
    },
    
    // CRITICAL: Map Mantine's semantic colors to our design-system.html colors
    white: '#e8e8e8',  // text-primary
    black: '#1a1a1a',  // bg-primary  
    primaryShade: { light: 6, dark: 6 },
    
    components: {
      Button: {
        defaultProps: {
          size: 'sm',
          radius: 'xs',
          variant: 'default', // Default to outline/default style
        },
        styles: (theme, props, u) => ({
          root: {
            height: rem(26), // Strict 26px height
            padding: `0 ${rem(12)}`,
            fontSize: rem(13),
            fontWeight: 500,
            // border: '1px solid transparent', // Let vars handle border
          },
        }),
        vars: (theme, props) => {
          // Primary/Filled Button -> Transparent with Border (Accent Color)
          if (props.variant === 'filled') {
            return {
              root: {
                '--button-bg': 'transparent',
                '--button-hover': 'rgba(var(--mantine-primary-color-rgb), 0.1)',
                '--button-color': 'var(--mantine-primary-color-filled)',
                '--button-bd': '1px solid var(--mantine-primary-color-filled)',
              }
            };
          }
          // Default/Outline Button -> Dark Grey with Light Border
          if (props.variant === 'default' || props.variant === 'outline') {
            return {
              root: {
                '--button-bg': 'transparent', // Use transparent for outline effect
                '--button-hover': 'var(--border-secondary)',
                '--button-color': 'var(--text-primary)',
                '--button-bd': '1px solid var(--border-secondary)',
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
            backgroundColor: 'var(--bg-quaternary)',
            borderColor: 'var(--border-secondary)',
            color: 'var(--text-primary)',
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
            backgroundColor: 'var(--bg-quaternary)',
            borderColor: 'var(--border-secondary)',
            color: 'var(--text-primary)',
            minHeight: rem(30),
            height: rem(30),
            fontSize: rem(13),
          },
          dropdown: {
            backgroundColor: 'var(--bg-secondary)',
            borderColor: 'var(--border-primary)',
          },
          option: {
            fontSize: rem(13),
            padding: '6px 10px',
            '&:hover': {
              backgroundColor: 'var(--border-primary)',
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
            backgroundColor: 'var(--bg-secondary)',
            border: '1px solid var(--border-primary)',
          },
          header: {
            backgroundColor: 'var(--bg-secondary)',
            borderBottom: '1px solid var(--border-primary)',
          }
        }
      },
      Stepper: {
        styles: {
          stepIcon: {
            borderRadius: '3px',
            borderWidth: '1px',
            backgroundColor: 'var(--bg-quaternary)',
            borderColor: 'var(--border-primary)',
            color: 'var(--text-secondary)'
          },
          separator: {
            backgroundColor: 'var(--border-primary)',
            height: '1px'
          },
          stepLabel: {
            fontSize: '13px',
            color: 'var(--text-primary)'
          },
          stepDescription: {
             fontSize: '11px',
             color: 'var(--text-tertiary)'
          }
        }
      }
    },
    
    other: {
      ...palette
    }
  });
};
