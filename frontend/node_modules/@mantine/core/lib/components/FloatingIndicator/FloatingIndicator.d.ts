import { BoxProps, ElementProps, Factory, StylesApiProps } from '../../core';
export type FloatingIndicatorStylesNames = 'root';
export type FloatingIndicatorCssVariables = {
    root: '--transition-duration';
};
export interface FloatingIndicatorProps extends BoxProps, StylesApiProps<FloatingIndicatorFactory>, ElementProps<'div'> {
    /** Target element over which indicator should be displayed */
    target: HTMLElement | null | undefined;
    /** Parent element with relative position based on which indicator position should be calculated */
    parent: HTMLElement | null | undefined;
    /** Transition duration in ms, `150` by default */
    transitionDuration?: number | string;
    /** Determines whether indicator should be displayed after transition ends, should be set if used inside a container that has `transform: scale(n)` styles */
    displayAfterTransitionEnd?: boolean;
}
export type FloatingIndicatorFactory = Factory<{
    props: FloatingIndicatorProps;
    ref: HTMLDivElement;
    stylesNames: FloatingIndicatorStylesNames;
    vars: FloatingIndicatorCssVariables;
}>;
export declare const FloatingIndicator: import("../../core").MantineComponent<{
    props: FloatingIndicatorProps;
    ref: HTMLDivElement;
    stylesNames: FloatingIndicatorStylesNames;
    vars: FloatingIndicatorCssVariables;
}>;
