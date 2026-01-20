import { colorPalettes } from './colors';

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
          },
        },
      },
      Table: {
        styles: {
          root: {
            fontSize: fontSizes.sm,
          },
        },
      },
      Card: {
        styles: {
          root: {
            borderRadius: radius.md,
          },
        },
      },
    },
  };
};
