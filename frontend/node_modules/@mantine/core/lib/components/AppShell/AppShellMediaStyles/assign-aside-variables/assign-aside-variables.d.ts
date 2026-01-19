import { MantineTheme } from '../../../../core';
import type { AppShellProps } from '../../AppShell';
import type { CSSVariables, MediaQueryVariables } from '../get-variables/get-variables';
interface AssignAsideVariablesInput {
    baseStyles: CSSVariables;
    minMediaStyles: MediaQueryVariables;
    maxMediaStyles: MediaQueryVariables;
    aside: AppShellProps['aside'] | undefined;
    theme: MantineTheme;
    mode: 'fixed' | 'static';
}
export declare function assignAsideVariables({ baseStyles, minMediaStyles, maxMediaStyles, aside, theme, mode, }: AssignAsideVariablesInput): void;
export {};
