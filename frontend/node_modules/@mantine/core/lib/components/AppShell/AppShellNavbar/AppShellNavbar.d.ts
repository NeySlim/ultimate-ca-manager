import { BoxProps, ElementProps, Factory, StylesApiProps } from '../../../core';
export type AppShellNavbarStylesNames = 'navbar';
export interface AppShellNavbarProps extends BoxProps, StylesApiProps<AppShellNavbarFactory>, ElementProps<'div'> {
    /** Determines whether component should have a border, overrides `withBorder` prop on `AppShell` component */
    withBorder?: boolean;
    /** Component `z-index`, by default inherited from the `AppShell` */
    zIndex?: string | number;
}
export type AppShellNavbarFactory = Factory<{
    props: AppShellNavbarProps;
    ref: HTMLElement;
    stylesNames: AppShellNavbarStylesNames;
}>;
export declare const AppShellNavbar: import("../../../core").MantineComponent<{
    props: AppShellNavbarProps;
    ref: HTMLElement;
    stylesNames: AppShellNavbarStylesNames;
}>;
