import { BoxProps, ElementProps, Factory, MantineSpacing, StylesApiProps } from '../../core';
export type GroupStylesNames = 'root';
export type GroupCssVariables = {
    root: '--group-gap' | '--group-align' | '--group-justify' | '--group-wrap' | '--group-child-width';
};
export interface GroupStylesCtx {
    childWidth: string;
}
export interface GroupProps extends BoxProps, StylesApiProps<GroupFactory>, ElementProps<'div'> {
    __size?: any;
    /** Controls `justify-content` CSS property, `'flex-start'` by default */
    justify?: React.CSSProperties['justifyContent'];
    /** Controls `align-items` CSS property, `'center'` by default */
    align?: React.CSSProperties['alignItems'];
    /** Controls `flex-wrap` CSS property, `'wrap'` by default */
    wrap?: React.CSSProperties['flexWrap'];
    /** Key of `theme.spacing` or any valid CSS value for `gap`, numbers are converted to rem, `'md'` by default */
    gap?: MantineSpacing;
    /** Determines whether each child element should have `flex-grow: 1` style, `false` by default */
    grow?: boolean;
    /** Determines whether children should take only dedicated amount of space (`max-width` style is set based on the number of children), `true` by default */
    preventGrowOverflow?: boolean;
}
export type GroupFactory = Factory<{
    props: GroupProps;
    ref: HTMLDivElement;
    stylesNames: GroupStylesNames;
    vars: GroupCssVariables;
    ctx: GroupStylesCtx;
}>;
export declare const Group: import("../../core").MantineComponent<{
    props: GroupProps;
    ref: HTMLDivElement;
    stylesNames: GroupStylesNames;
    vars: GroupCssVariables;
    ctx: GroupStylesCtx;
}>;
