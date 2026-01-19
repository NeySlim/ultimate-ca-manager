import { BoxProps, ElementProps, Factory, MantineColor, MantineRadius, StylesApiProps } from '../../core';
export type BlockquoteStylesNames = 'root' | 'icon' | 'cite';
export type BlockquoteCssVariables = {
    root: '--bq-bg-light' | '--bq-bg-dark' | '--bq-bd' | '--bq-icon-size' | '--bq-radius';
};
export interface BlockquoteProps extends BoxProps, StylesApiProps<BlockquoteFactory>, ElementProps<'blockquote', 'cite'> {
    /** Blockquote icon, displayed on the top left */
    icon?: React.ReactNode;
    /** Controls icon `width` and `height`, numbers are converted to rem, `40` by default */
    iconSize?: number | string;
    /** Key of `theme.colors` or any valid CSS color, `theme.primaryColor` by default */
    color?: MantineColor;
    /** Key of `theme.radius` or any valid CSS value to set `border-radius`, `theme.defaultRadius` by default */
    radius?: MantineRadius;
    /** Reference to a cited quote */
    cite?: React.ReactNode;
}
export type BlockquoteFactory = Factory<{
    props: BlockquoteProps;
    ref: HTMLQuoteElement;
    stylesNames: BlockquoteStylesNames;
    vars: BlockquoteCssVariables;
}>;
export declare const Blockquote: import("../../core").MantineComponent<{
    props: BlockquoteProps;
    ref: HTMLQuoteElement;
    stylesNames: BlockquoteStylesNames;
    vars: BlockquoteCssVariables;
}>;
