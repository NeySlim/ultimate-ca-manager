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
    defaultRadius: 'sm',
    fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
    fontFamilyMonospace: 'JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    
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
          radius: 'sm',
        },
        styles: {
          root: {
            fontWeight: 500,
          }
        }
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
