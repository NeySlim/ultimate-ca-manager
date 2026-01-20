import { createTheme, rem } from '@mantine/core';
import { colorPalettes } from './colors';

// Helper to generate 10 shades from a single color
// In a real app we might want more specific control, but this works for a start
// We mostly use the explicit primary/secondary colors anyway.
const generateShades = (color) => [
  '#f0f4f8', // 0 (lightest)
  '#dbe4ef',
  '#c0d0e3',
  '#a2bbd6',
  '#82a5c9',
  color,     // 5 (primary) - This is where Mantine picks defaults
  '#4a7fb7',
  '#3b6aa3',
  '#2d568f',
  '#20427a'  // 9 (darkest)
];

export const createAppTheme = (paletteKey = 'blueSky') => {
  const palette = colorPalettes[paletteKey] || colorPalettes['blueSky'];

  return createTheme({
    primaryColor: 'brand',
    defaultRadius: 'xs', // STRICT: 3px as per UI_CONTEXT.md
    fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
    fontFamilyMonospace: 'JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    
    // Explicit sizing to match "Dense" look
    fontSizes: {
      xs: rem(11),
      sm: rem(13), // Standard UI text
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
        '#C1C2C5', // 0
        '#A6A7AB', // 1
        '#909296', // 2
        '#5C5F66', // 3
        '#373A40', // 4
        '#2C2E33', // 5
        '#25262B', // 6
        '#1A1B1E', // 7 (Standard Mantine Dark) -> We use #1a1a1a from design
        '#141517', // 8
        '#101113', // 9
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
      }
    },
    
    other: {
      ...palette
    }
  });
};
