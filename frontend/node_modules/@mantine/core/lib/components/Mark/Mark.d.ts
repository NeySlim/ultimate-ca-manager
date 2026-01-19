import { BoxProps, ElementProps, Factory, MantineColor, StylesApiProps } from '../../core';
export type MarkStylesNames = 'root';
export type MarkCssVariables = {
    root: '--mark-bg-dark' | '--mark-bg-light';
};
export interface MarkProps extends BoxProps, StylesApiProps<MarkFactory>, ElementProps<'mark'> {
    /** Key of `theme.colors` or any valid CSS color, `yellow` by default */
    color?: MantineColor;
}
export type MarkFactory = Factory<{
    props: MarkProps;
    ref: HTMLElement;
    stylesNames: MarkStylesNames;
    vars: MarkCssVariables;
}>;
export declare const Mark: import("../../core").MantineComponent<{
    props: MarkProps;
    ref: HTMLElement;
    stylesNames: MarkStylesNames;
    vars: MarkCssVariables;
}>;
