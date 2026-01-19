import { BoxProps, ElementProps, Factory, MantineColor, StylesApiProps } from '../../core';
export type CodeStylesNames = 'root';
export type CodeCssVariables = {
    root: '--code-bg';
};
export interface CodeProps extends BoxProps, StylesApiProps<CodeFactory>, ElementProps<'code'> {
    /** Key of `theme.colors` or any valid CSS color, controls `background-color` of the code, by default value is calculated based on color scheme */
    color?: MantineColor;
    /** If set code will be rendered inside `pre`, `false` by default */
    block?: boolean;
}
export type CodeFactory = Factory<{
    props: CodeProps;
    ref: HTMLElement;
    stylesNames: CodeStylesNames;
    vars: CodeCssVariables;
}>;
export declare const Code: import("../../core").MantineComponent<{
    props: CodeProps;
    ref: HTMLElement;
    stylesNames: CodeStylesNames;
    vars: CodeCssVariables;
}>;
