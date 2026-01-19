import { BoxProps, ElementProps, Factory, StylesApiProps } from '../../../core';
export type AppShellAsideStylesNames = 'aside';
export interface AppShellAsideProps extends BoxProps, StylesApiProps<AppShellAsideFactory>, ElementProps<'aside'> {
    /** Determines whether component should have a border, overrides `withBorder` prop on `AppShell` component */
    withBorder?: boolean;
    /** Component `z-index`, by default inherited from the `AppShell` */
    zIndex?: string | number;
}
export type AppShellAsideFactory = Factory<{
    props: AppShellAsideProps;
    ref: HTMLElement;
    stylesNames: AppShellAsideStylesNames;
}>;
export declare const AppShellAside: import("../../../core").MantineComponent<{
    props: AppShellAsideProps;
    ref: HTMLElement;
    stylesNames: AppShellAsideStylesNames;
}>;
