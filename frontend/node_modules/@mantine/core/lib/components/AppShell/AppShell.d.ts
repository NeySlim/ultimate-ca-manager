import { BoxProps, ElementProps, Factory, MantineSpacing, StylesApiProps } from '../../core';
import { AppShellAsideConfiguration, AppShellFooterConfiguration, AppShellHeaderConfiguration, AppShellNavbarConfiguration, AppShellResponsiveSize } from './AppShell.types';
import { AppShellAside } from './AppShellAside/AppShellAside';
import { AppShellFooter } from './AppShellFooter/AppShellFooter';
import { AppShellHeader } from './AppShellHeader/AppShellHeader';
import { AppShellMain } from './AppShellMain/AppShellMain';
import { AppShellNavbar } from './AppShellNavbar/AppShellNavbar';
import { AppShellSection } from './AppShellSection/AppShellSection';
export type AppShellStylesNames = 'root' | 'navbar' | 'main' | 'header' | 'footer' | 'aside' | 'section';
export type AppShellCssVariables = {
    root: '--app-shell-transition-duration' | '--app-shell-transition-timing-function';
};
export interface AppShellProps extends BoxProps, StylesApiProps<AppShellFactory>, ElementProps<'div'> {
    /** Determines whether associated components should have a border, `true` by default */
    withBorder?: boolean;
    /** Controls padding of the main section, `0` by default. !important!: use `padding` prop instead of `p`. */
    padding?: MantineSpacing | AppShellResponsiveSize;
    /** AppShell.Navbar configuration, controls width, breakpoints and collapsed state. Required if you use AppShell.Navbar component. */
    navbar?: AppShellNavbarConfiguration;
    /** AppShell.Aside configuration, controls width, breakpoints and collapsed state. Required if you use AppShell.Aside component. */
    aside?: AppShellAsideConfiguration;
    /** AppShell.Header configuration, controls height, offset and collapsed state. Required if you use AppShell.Header component. */
    header?: AppShellHeaderConfiguration;
    /** AppShell.Footer configuration, controls height, offset and collapsed state. Required if you use AppShell.Footer component. */
    footer?: AppShellFooterConfiguration;
    /** Duration of all transitions in ms, `200` by default */
    transitionDuration?: number;
    /** Timing function of all transitions, `ease` by default */
    transitionTimingFunction?: React.CSSProperties['transitionTimingFunction'];
    /** `z-index` of all associated elements, `100` by default */
    zIndex?: string | number;
    /** Determines how Navbar/Aside are arranged relative to Header/Footer, `default` by default */
    layout?: 'default' | 'alt';
    /** If set, Navbar, Aside, Header and Footer components be hidden */
    disabled?: boolean;
    /** Determines whether Header and Footer components should include styles to offset scrollbars. Based on `react-remove-scroll`. `true` by default for `layout="default"`, `false` for `layout="alt"` */
    offsetScrollbars?: boolean;
}
export type AppShellFactory = Factory<{
    props: AppShellProps;
    ref: HTMLDivElement;
    stylesNames: AppShellStylesNames;
    vars: AppShellCssVariables;
    staticComponents: {
        Navbar: typeof AppShellNavbar;
        Header: typeof AppShellHeader;
        Main: typeof AppShellMain;
        Aside: typeof AppShellAside;
        Footer: typeof AppShellFooter;
        Section: typeof AppShellSection;
    };
}>;
export declare const AppShell: import("../../core").MantineComponent<{
    props: AppShellProps;
    ref: HTMLDivElement;
    stylesNames: AppShellStylesNames;
    vars: AppShellCssVariables;
    staticComponents: {
        Navbar: typeof AppShellNavbar;
        Header: typeof AppShellHeader;
        Main: typeof AppShellMain;
        Aside: typeof AppShellAside;
        Footer: typeof AppShellFooter;
        Section: typeof AppShellSection;
    };
}>;
