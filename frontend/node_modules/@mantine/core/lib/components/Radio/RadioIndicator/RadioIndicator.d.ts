import { BoxProps, ElementProps, Factory, MantineColor, MantineRadius, MantineSize, StylesApiProps } from '../../../core';
import { RadioIconProps } from '../RadioIcon';
export type RadioIndicatorStylesNames = 'indicator' | 'icon';
export type RadioIndicatorVariant = 'filled' | 'outline';
export type RadioIndicatorCssVariables = {
    indicator: '--radio-size' | '--radio-radius' | '--radio-color' | '--radio-icon-color' | '--radio-icon-size';
};
export interface RadioIndicatorProps extends BoxProps, StylesApiProps<RadioIndicatorFactory>, ElementProps<'div'> {
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
    /** A component that replaces default check icon */
    icon?: React.FC<RadioIconProps>;
    /** Determines whether the component should have checked styles */
    checked?: boolean;
    /** Determines whether the component should have disabled styles */
    disabled?: boolean;
}
export type RadioIndicatorFactory = Factory<{
    props: RadioIndicatorProps;
    ref: HTMLDivElement;
    stylesNames: RadioIndicatorStylesNames;
    vars: RadioIndicatorCssVariables;
    variant: RadioIndicatorVariant;
}>;
export declare const RadioIndicator: import("../../../core").MantineComponent<{
    props: RadioIndicatorProps;
    ref: HTMLDivElement;
    stylesNames: RadioIndicatorStylesNames;
    vars: RadioIndicatorCssVariables;
    variant: RadioIndicatorVariant;
}>;
