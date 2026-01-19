import { BoxProps, ElementProps, Factory, MantineColor, StylesApiProps } from '../../core';
export type SemiCircleProgressStylesNames = 'root' | 'svg' | 'emptySegment' | 'filledSegment' | 'label';
export type SemiCircleProgressCssVariables = {
    root: '--scp-filled-segment-color' | '--scp-empty-segment-color' | '--scp-rotation' | '--scp-transition-duration' | '--scp-thickness';
};
export interface SemiCircleProgressProps extends BoxProps, StylesApiProps<SemiCircleProgressFactory>, ElementProps<'div'> {
    /** Progress value from `0` to `100` */
    value: number;
    /** Diameter of the svg in px, `200` by default */
    size?: number;
    /** Circle thickness in px, `12` by default */
    thickness?: number;
    /** Orientation of the circle, `'up'` by default */
    orientation?: 'up' | 'down';
    /** Direction from which the circle is filled, `'left-to-right'` by default */
    fillDirection?: 'right-to-left' | 'left-to-right';
    /** Key of `theme.colors` or any valid CSS color value, `theme.primaryColor` by default */
    filledSegmentColor?: MantineColor;
    /** Key of `theme.colors` or any valid CSS color value, by default the value is determined based on the color scheme value */
    emptySegmentColor?: MantineColor;
    /** Transition duration of filled section styles changes in ms, `0` by default */
    transitionDuration?: number;
    /** Label rendered inside the circle */
    label?: React.ReactNode;
    /** Label position relative to the circle center, `'bottom'` by default */
    labelPosition?: 'center' | 'bottom';
}
export type SemiCircleProgressFactory = Factory<{
    props: SemiCircleProgressProps;
    ref: HTMLDivElement;
    stylesNames: SemiCircleProgressStylesNames;
    vars: SemiCircleProgressCssVariables;
}>;
export declare const SemiCircleProgress: import("../../core").MantineComponent<{
    props: SemiCircleProgressProps;
    ref: HTMLDivElement;
    stylesNames: SemiCircleProgressStylesNames;
    vars: SemiCircleProgressCssVariables;
}>;
