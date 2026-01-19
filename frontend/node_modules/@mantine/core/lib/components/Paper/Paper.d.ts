import { BoxProps, MantineRadius, MantineShadow, PolymorphicFactory, StylesApiProps } from '../../core';
export type PaperStylesNames = 'root';
export type PaperCssVariables = {
    root: '--paper-radius' | '--paper-shadow';
};
export interface PaperBaseProps {
    /** Key of `theme.shadows` or any valid CSS value to set `box-shadow`, `none` by default */
    shadow?: MantineShadow;
    /** Key of `theme.radius` or any valid CSS value to set border-radius, numbers are converted to rem, `theme.defaultRadius` by default */
    radius?: MantineRadius;
    /** Determines whether the paper should have border, border color depends on color scheme, `false` by default */
    withBorder?: boolean;
}
export interface PaperProps extends BoxProps, PaperBaseProps, StylesApiProps<PaperFactory> {
}
export type PaperFactory = PolymorphicFactory<{
    props: PaperProps;
    defaultComponent: 'div';
    defaultRef: HTMLDivElement;
    stylesNames: PaperStylesNames;
    vars: PaperCssVariables;
}>;
export declare const Paper: (<C = "div">(props: import("../../core").PolymorphicComponentProps<C, PaperProps>) => React.ReactElement) & Omit<import("react").FunctionComponent<(PaperProps & {
    component?: any;
} & Omit<Omit<any, "ref">, "component" | keyof PaperProps> & {
    ref?: any;
    renderRoot?: (props: any) => any;
}) | (PaperProps & {
    component: React.ElementType;
    renderRoot?: (props: Record<string, any>) => any;
})>, never> & import("../../core/factory/factory").ThemeExtend<{
    props: PaperProps;
    defaultComponent: "div";
    defaultRef: HTMLDivElement;
    stylesNames: PaperStylesNames;
    vars: PaperCssVariables;
}> & import("../../core/factory/factory").ComponentClasses<{
    props: PaperProps;
    defaultComponent: "div";
    defaultRef: HTMLDivElement;
    stylesNames: PaperStylesNames;
    vars: PaperCssVariables;
}> & import("../../core/factory/polymorphic-factory").PolymorphicComponentWithProps<{
    props: PaperProps;
    defaultComponent: "div";
    defaultRef: HTMLDivElement;
    stylesNames: PaperStylesNames;
    vars: PaperCssVariables;
}> & Record<string, never>;
