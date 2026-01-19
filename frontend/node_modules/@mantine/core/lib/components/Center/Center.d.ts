import { BoxProps, PolymorphicFactory, StylesApiProps } from '../../core';
export type CenterStylesNames = 'root';
export interface CenterProps extends BoxProps, StylesApiProps<CenterFactory> {
    /** Content that should be centered vertically and horizontally */
    children?: React.ReactNode;
    /** Determines whether `inline-flex` should be used instead of `flex`, `false` by default */
    inline?: boolean;
}
export type CenterFactory = PolymorphicFactory<{
    props: CenterProps;
    defaultRef: HTMLDivElement;
    defaultComponent: 'div';
    stylesNames: CenterStylesNames;
}>;
export declare const Center: (<C = "div">(props: import("../../core").PolymorphicComponentProps<C, CenterProps>) => React.ReactElement) & Omit<import("react").FunctionComponent<(CenterProps & {
    component?: any;
} & Omit<Omit<any, "ref">, "component" | keyof CenterProps> & {
    ref?: any;
    renderRoot?: (props: any) => any;
}) | (CenterProps & {
    component: React.ElementType;
    renderRoot?: (props: Record<string, any>) => any;
})>, never> & import("../../core/factory/factory").ThemeExtend<{
    props: CenterProps;
    defaultRef: HTMLDivElement;
    defaultComponent: "div";
    stylesNames: CenterStylesNames;
}> & import("../../core/factory/factory").ComponentClasses<{
    props: CenterProps;
    defaultRef: HTMLDivElement;
    defaultComponent: "div";
    stylesNames: CenterStylesNames;
}> & import("../../core/factory/polymorphic-factory").PolymorphicComponentWithProps<{
    props: CenterProps;
    defaultRef: HTMLDivElement;
    defaultComponent: "div";
    stylesNames: CenterStylesNames;
}> & Record<string, never>;
