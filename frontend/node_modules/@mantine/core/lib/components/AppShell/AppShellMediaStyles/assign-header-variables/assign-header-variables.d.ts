import type { AppShellProps } from '../../AppShell';
import type { CSSVariables, MediaQueryVariables } from '../get-variables/get-variables';
interface AssignHeaderVariablesInput {
    baseStyles: CSSVariables;
    minMediaStyles: MediaQueryVariables;
    header: AppShellProps['header'] | undefined;
    mode: 'fixed' | 'static';
}
export declare function assignHeaderVariables({ baseStyles, minMediaStyles, header, mode, }: AssignHeaderVariablesInput): void;
export {};
