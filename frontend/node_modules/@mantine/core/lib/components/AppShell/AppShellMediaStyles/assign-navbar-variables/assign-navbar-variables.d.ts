import { MantineTheme } from '../../../../core';
import type { AppShellProps } from '../../AppShell';
import type { CSSVariables, MediaQueryVariables } from '../get-variables/get-variables';
interface AssignNavbarVariablesInput {
    baseStyles: CSSVariables;
    minMediaStyles: MediaQueryVariables;
    maxMediaStyles: MediaQueryVariables;
    navbar: AppShellProps['navbar'] | undefined;
    theme: MantineTheme;
    mode: 'fixed' | 'static';
}
export declare function assignNavbarVariables({ baseStyles, minMediaStyles, maxMediaStyles, navbar, theme, mode, }: AssignNavbarVariablesInput): void;
export {};
