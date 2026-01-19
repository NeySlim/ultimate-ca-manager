import { BoxProps, ElementProps, Factory, StylesApiProps } from '../../core';
export type AspectRatioStylesNames = 'root';
export type AspectRatioCssVariables = {
    root: '--ar-ratio';
};
export interface AspectRatioProps extends BoxProps, StylesApiProps<AspectRatioFactory>, ElementProps<'div'> {
    /** Aspect ratio, e.g. `16 / 9`, `4 / 3`, `1920 / 1080`, `1` by default */
    ratio?: number;
}
export type AspectRatioFactory = Factory<{
    props: AspectRatioProps;
    ref: HTMLDivElement;
    stylesNames: AspectRatioStylesNames;
    vars: AspectRatioCssVariables;
}>;
export declare const AspectRatio: import("../../core").MantineComponent<{
    props: AspectRatioProps;
    ref: HTMLDivElement;
    stylesNames: AspectRatioStylesNames;
    vars: AspectRatioCssVariables;
}>;
