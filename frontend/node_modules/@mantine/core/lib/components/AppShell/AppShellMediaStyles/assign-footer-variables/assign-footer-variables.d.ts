import type { AppShellProps } from '../../AppShell';
import type { CSSVariables, MediaQueryVariables } from '../get-variables/get-variables';
interface AssignFooterVariablesInput {
    baseStyles: CSSVariables;
    minMediaStyles: MediaQueryVariables;
    footer: AppShellProps['footer'] | undefined;
    mode: 'fixed' | 'static';
}
export declare function assignFooterVariables({ baseStyles, minMediaStyles, footer, mode, }: AssignFooterVariablesInput): void;
export {};
