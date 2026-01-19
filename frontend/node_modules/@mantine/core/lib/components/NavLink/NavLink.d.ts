import { BoxProps, MantineColor, MantineSpacing, PolymorphicFactory, StylesApiProps } from '../../core';
export type NavLinkStylesNames = 'root' | 'section' | 'body' | 'label' | 'description' | 'chevron' | 'collapse' | 'children';
export type NavLinkVariant = 'filled' | 'light' | 'subtle';
export type NavLinkCssVariables = {
    root: '--nl-color' | '--nl-bg' | '--nl-hover';
    children: '--nl-offset';
};
export interface NavLinkProps extends BoxProps, StylesApiProps<NavLinkFactory> {
    /** Main link label */
    label?: React.ReactNode;
    /** Link description, displayed below the label */
    description?: React.ReactNode;
    /** Section displayed on the left side of the label */
    leftSection?: React.ReactNode;
    /** Section displayed on the right side of the label */
    rightSection?: React.ReactNode;
    /** Determines whether the link should have active styles, `false` by default */
    active?: boolean;
    /** Key of `theme.colors` of any valid CSS color to control active styles, `theme.primaryColor` by default */
    color?: MantineColor;
    /** If set, label and description will not wrap to the next line, `false` by default */
    noWrap?: boolean;
    /** Child `NavLink` components */
    children?: React.ReactNode;
    /** Controlled nested items collapse state */
    opened?: boolean;
    /** Uncontrolled nested items collapse initial state */
    defaultOpened?: boolean;
    /** Called when open state changes */
    onChange?: (opened: boolean) => void;
    /** If set, right section will not be rotated when collapse is opened, `false` by default */
    disableRightSectionRotation?: boolean;
    /** Key of `theme.spacing` or any valid CSS value to set collapsed links `padding-left`, `'lg'` by default */
    childrenOffset?: MantineSpacing;
    /** If set, disabled styles will be added to the root element, `false` by default */
    disabled?: boolean;
    /** Called when the link is clicked */
    onClick?: (event: React.MouseEvent<HTMLAnchorElement>) => void;
    /** Link `onkeydown` event */
    onKeyDown?: (event: React.KeyboardEvent<HTMLAnchorElement>) => void;
    /** Determines whether button text color with filled variant should depend on `background-color`. If luminosity of the `color` prop is less than `theme.luminosityThreshold`, then `theme.white` will be used for text color, otherwise `theme.black`. Overrides `theme.autoContrast`. */
    autoContrast?: boolean;
}
export type NavLinkFactory = PolymorphicFactory<{
    props: NavLinkProps;
    defaultRef: HTMLAnchorElement;
    defaultComponent: 'a';
    stylesNames: NavLinkStylesNames;
    vars: NavLinkCssVariables;
    variant: NavLinkVariant;
}>;
export declare const NavLink: (<C = "a">(props: import("../../core").PolymorphicComponentProps<C, NavLinkProps>) => React.ReactElement) & Omit<import("react").FunctionComponent<(NavLinkProps & {
    component?: any;
} & Omit<Omit<any, "ref">, keyof NavLinkProps | "component"> & {
    ref?: any;
    renderRoot?: (props: any) => any;
}) | (NavLinkProps & {
    component: React.ElementType;
    renderRoot?: (props: Record<string, any>) => any;
})>, never> & import("../../core/factory/factory").ThemeExtend<{
    props: NavLinkProps;
    defaultRef: HTMLAnchorElement;
    defaultComponent: "a";
    stylesNames: NavLinkStylesNames;
    vars: NavLinkCssVariables;
    variant: NavLinkVariant;
}> & import("../../core/factory/factory").ComponentClasses<{
    props: NavLinkProps;
    defaultRef: HTMLAnchorElement;
    defaultComponent: "a";
    stylesNames: NavLinkStylesNames;
    vars: NavLinkCssVariables;
    variant: NavLinkVariant;
}> & import("../../core/factory/polymorphic-factory").PolymorphicComponentWithProps<{
    props: NavLinkProps;
    defaultRef: HTMLAnchorElement;
    defaultComponent: "a";
    stylesNames: NavLinkStylesNames;
    vars: NavLinkCssVariables;
    variant: NavLinkVariant;
}> & Record<string, never>;
