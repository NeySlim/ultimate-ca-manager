import { BoxProps, ElementProps, Factory, StylesApiProps } from '../../../core';
export type AppShellHeaderStylesNames = 'header';
export interface AppShellHeaderProps extends BoxProps, StylesApiProps<AppShellHeaderFactory>, ElementProps<'header'> {
    /** Determines whether component should have a border, overrides `withBorder` prop on `AppShell` component */
    withBorder?: boolean;
    /** Component `z-index`, by default inherited from the `AppShell` */
    zIndex?: string | number;
}
export type AppShellHeaderFactory = Factory<{
    props: AppShellHeaderProps;
    ref: HTMLElement;
    stylesNames: AppShellHeaderStylesNames;
}>;
export declare const AppShellHeader: import("../../../core").MantineComponent<{
    props: AppShellHeaderProps;
    ref: HTMLElement;
    stylesNames: AppShellHeaderStylesNames;
}>;
