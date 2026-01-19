import { BoxProps, ElementProps, Factory, MantineRadius, MantineSize, StylesApiProps } from '../../../core';
export type ProgressRootStylesNames = 'root' | 'section' | 'label';
export type ProgressRootCssVariables = {
    root: '--progress-size' | '--progress-radius' | '--progress-transition-duration';
};
export interface __ProgressRootProps extends BoxProps, ElementProps<'div'> {
    /** Controls track height, `'md'` by default */
    size?: MantineSize | (string & {}) | number;
    /** Key of `theme.radius` or any valid CSS value to set `border-radius`, `theme.defaultRadius` by default */
    radius?: MantineRadius;
    /** Determines whether label text color should depend on `background-color`. If luminosity of the `color` prop is less than `theme.luminosityThreshold`, then `theme.white` will be used for text color, otherwise `theme.black`. Overrides `theme.autoContrast`. */
    autoContrast?: boolean;
    /** Controls sections width transition duration, value is specified in ms, `100` by default */
    transitionDuration?: number;
}
export interface ProgressRootProps extends __ProgressRootProps, StylesApiProps<ProgressRootFactory> {
}
export type ProgressRootFactory = Factory<{
    props: ProgressRootProps;
    ref: HTMLDivElement;
    stylesNames: ProgressRootStylesNames;
    vars: ProgressRootCssVariables;
}>;
export declare const ProgressRoot: import("../../../core").MantineComponent<{
    props: ProgressRootProps;
    ref: HTMLDivElement;
    stylesNames: ProgressRootStylesNames;
    vars: ProgressRootCssVariables;
}>;
