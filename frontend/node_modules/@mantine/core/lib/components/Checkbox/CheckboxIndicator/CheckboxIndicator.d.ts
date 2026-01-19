import { BoxProps, ElementProps, Factory, MantineColor, MantineRadius, MantineSize, StylesApiProps } from '../../../core';
export type CheckboxIndicatorStylesNames = 'indicator' | 'icon';
export type CheckboxIndicatorVariant = 'filled' | 'outline';
export type CheckboxIndicatorCssVariables = {
    indicator: '--checkbox-size' | '--checkbox-radius' | '--checkbox-color' | '--checkbox-icon-color';
};
export interface CheckboxIndicatorProps extends BoxProps, StylesApiProps<CheckboxIndicatorFactory>, ElementProps<'div'> {
    /** Key of `theme.colors` or any valid CSS color to set input background color in checked state, `theme.primaryColor` by default */
    color?: MantineColor;
    /** Controls size of the component, `'sm'` by default */
    size?: MantineSize | (string & {});
    /** Key of `theme.radius` or any valid CSS value to set `border-radius,` `theme.defaultRadius` by default */
    radius?: MantineRadius;
    /** Key of `theme.colors` or any valid CSS color to set icon color, by default value depends on `theme.autoContrast` */
    iconColor?: MantineColor;
    /** Determines whether icon color with filled variant should depend on `background-color`. If luminosity of the `color` prop is less than `theme.luminosityThreshold`, then `theme.white` will be used for text color, otherwise `theme.black`. Overrides `theme.autoContrast`. */
    autoContrast?: boolean;
    /** Indeterminate state of the checkbox. If set, `checked` prop is ignored. */
    indeterminate?: boolean;
    /** Icon displayed when checkbox is in checked or indeterminate state */
    icon?: React.FC<{
        indeterminate: boolean | undefined;
        className: string;
    }>;
    /** Determines whether the component should have checked styles */
    checked?: boolean;
    /** Determines whether the component should have disabled styles */
    disabled?: boolean;
}
export type CheckboxIndicatorFactory = Factory<{
    props: CheckboxIndicatorProps;
    ref: HTMLDivElement;
    stylesNames: CheckboxIndicatorStylesNames;
    vars: CheckboxIndicatorCssVariables;
    variant: CheckboxIndicatorVariant;
}>;
export declare const CheckboxIndicator: import("../../../core").MantineComponent<{
    props: CheckboxIndicatorProps;
    ref: HTMLDivElement;
    stylesNames: CheckboxIndicatorStylesNames;
    vars: CheckboxIndicatorCssVariables;
    variant: CheckboxIndicatorVariant;
}>;
