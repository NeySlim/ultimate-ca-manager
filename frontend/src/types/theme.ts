/**
 * Theme System Types
 * UCM - Ultimate Certificate Manager
 */

export type ColorPalette =
  | 'teal'
  | 'blue'
  | 'indigo'
  | 'slate'
  | 'purple'
  | 'emerald'
  | 'amber'
  | 'terracotta'
  | 'mokka'
  | 'copper'
  | 'rust'
  | 'caramel';

export type ColorScheme = 'light' | 'dark';

export type DensityLevel = 'compact' | 'normal' | 'comfortable';

export interface ThemeConfig {
  palette: ColorPalette;
  colorScheme: ColorScheme;
  density: DensityLevel;
}

export interface DensityConfig {
  spacing: {
    xs: number;
    sm: number;
    md: number;
    lg: number;
    xl: number;
  };
  fontSize: {
    xs: number;
    sm: number;
    md: number;
    lg: number;
    xl: number;
  };
  radius: {
    xs: number;
    sm: number;
    md: number;
    lg: number;
    xl: number;
  };
  inputHeight: {
    xs: number;
    sm: number;
    md: number;
    lg: number;
    xl: number;
  };
}

export interface PaletteColors {
  50: string;
  100: string;
  200: string;
  300: string;
  400: string;
  500: string;
  600: string;
  700: string;
  800: string;
  900: string;
  950: string;
}
