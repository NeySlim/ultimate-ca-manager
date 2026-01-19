import { BoxProps, ElementProps, Factory, MantineColor, MantineRadius, StylesApiProps } from '../../core';
import { IndicatorPosition } from './Indicator.types';
export type IndicatorPositionVariables = '--indicator-top' | '--indicator-bottom' | '--indicator-left' | '--indicator-right' | '--indicator-translate-x' | '--indicator-translate-y';
export type IndicatorStylesNames = 'root' | 'indicator';
export type IndicatorCssVariables = {
    root: '--indicator-color' | '--indicator-text-color' | '--indicator-size' | '--indicator-radius' | '--indicator-z-index' | IndicatorPositionVariables;
};
export interface IndicatorProps extends BoxProps, StylesApiProps<IndicatorFactory>, ElementProps<'div'> {
    /** Indicator position relative to the target element, `'top-end'` by default */
    position?: IndicatorPosition;
    /** Indicator offset relative to the target element, usually used for elements with border-radius, equals to `size` by default */
    offset?: number;
    /** Determines whether the indicator container should be an inline element, `false` by default */
    inline?: boolean;
    /** Indicator width and height, `10` by default */
    size?: number | string;
    /** Label rendered inside the indicator, for example, notification count */
    label?: React.ReactNode;
    /** Key of `theme.radius` or any valid CSS value to set `border-radius`, `100` by default */
    radius?: MantineRadius;
    /** Key of `theme.colors` or any valid CSS color value, `theme.primaryColor` by default */
    color?: MantineColor;
    /** Determines whether the indicator should have a border (color of the border is the same as the body element), `false` by default */
    withBorder?: boolean;
    /** When Indicator is disabled it renders children only */
    disabled?: boolean;
    /** Determines whether the indicator should have processing animation, `false` by default */
    processing?: boolean;
    /** Indicator z-index, `200` by default */
    zIndex?: string | number;
    /** Determines whether text color should depend on `background-color`. If luminosity of the `color` prop is less than `theme.luminosityThreshold`, then `theme.white` will be used for text color, otherwise `theme.black`. Overrides `theme.autoContrast`. */
    autoContrast?: boolean;
}
export type IndicatorFactory = Factory<{
    props: IndicatorProps;
    ref: HTMLDivElement;
    stylesNames: IndicatorStylesNames;
    vars: IndicatorCssVariables;
}>;
export declare const Indicator: import("../../core").MantineComponent<{
    props: IndicatorProps;
    ref: HTMLDivElement;
    stylesNames: IndicatorStylesNames;
    vars: IndicatorCssVariables;
}>;
