import { PolymorphicFactory } from '../../core';
import { TextCssVariables, TextProps, TextStylesNames, TextVariant } from '../Text';
export type AnchorStylesNames = TextStylesNames;
export type AnchorVariant = TextVariant;
export type AnchorCssVariables = TextCssVariables;
export interface AnchorProps extends Omit<TextProps, 'span'> {
    /** Determines in which cases link should have `text-decoration: underline` styles, `hover` by default */
    underline?: 'always' | 'hover' | 'not-hover' | 'never';
}
export type AnchorFactory = PolymorphicFactory<{
    props: AnchorProps;
    defaultComponent: 'a';
    defaultRef: HTMLAnchorElement;
    stylesNames: AnchorStylesNames;
    vars: AnchorCssVariables;
    variant: AnchorVariant;
}>;
export declare const Anchor: (<C = "a">(props: import("../../core").PolymorphicComponentProps<C, AnchorProps>) => React.ReactElement) & Omit<import("react").FunctionComponent<(AnchorProps & {
    component?: any;
} & Omit<Omit<any, "ref">, "component" | keyof AnchorProps> & {
    ref?: any;
    renderRoot?: (props: any) => any;
}) | (AnchorProps & {
    component: React.ElementType;
    renderRoot?: (props: Record<string, any>) => any;
})>, never> & import("../../core/factory/factory").ThemeExtend<{
    props: AnchorProps;
    defaultComponent: "a";
    defaultRef: HTMLAnchorElement;
    stylesNames: AnchorStylesNames;
    vars: AnchorCssVariables;
    variant: AnchorVariant;
}> & import("../../core/factory/factory").ComponentClasses<{
    props: AnchorProps;
    defaultComponent: "a";
    defaultRef: HTMLAnchorElement;
    stylesNames: AnchorStylesNames;
    vars: AnchorCssVariables;
    variant: AnchorVariant;
}> & import("../../core/factory/polymorphic-factory").PolymorphicComponentWithProps<{
    props: AnchorProps;
    defaultComponent: "a";
    defaultRef: HTMLAnchorElement;
    stylesNames: AnchorStylesNames;
    vars: AnchorCssVariables;
    variant: AnchorVariant;
}> & Record<string, never>;
