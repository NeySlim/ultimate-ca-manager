import { BoxProps, ElementProps, Factory, MantineSpacing, StyleProp, StylesApiProps } from '../../core';
import { GridBreakpoints } from './Grid.context';
import { GridCol } from './GridCol/GridCol';
export type GridStylesNames = 'root' | 'col' | 'inner' | 'container';
export type GridCssVariables = {
    root: '--grid-justify' | '--grid-align' | '--grid-overflow';
};
export interface GridProps extends BoxProps, StylesApiProps<GridFactory>, ElementProps<'div'> {
    /** Gutter between columns, key of `theme.spacing` or any valid CSS value, `'md'` by default */
    gutter?: StyleProp<MantineSpacing>;
    /** Determines whether columns in the last row should expand to fill all available space, `false` by default */
    grow?: boolean;
    /** Sets `justify-content`, `flex-start` by default */
    justify?: React.CSSProperties['justifyContent'];
    /** Sets `align-items`, `stretch` by default */
    align?: React.CSSProperties['alignItems'];
    /** Number of columns in each row, `12` by default */
    columns?: number;
    /** Sets `overflow` CSS property on the root element, `'visible'` by default */
    overflow?: React.CSSProperties['overflow'];
    /** Determines typeof of queries that are used for responsive styles, `'media'` by default */
    type?: 'media' | 'container';
    /** Breakpoints values, only applicable when `type="container"` is set, ignored when `type` is not set or `type="media"` is set. */
    breakpoints?: GridBreakpoints;
}
export type GridFactory = Factory<{
    props: GridProps;
    ref: HTMLDivElement;
    stylesNames: GridStylesNames;
    vars: GridCssVariables;
    staticComponents: {
        Col: typeof GridCol;
    };
}>;
export declare const Grid: import("../../core").MantineComponent<{
    props: GridProps;
    ref: HTMLDivElement;
    stylesNames: GridStylesNames;
    vars: GridCssVariables;
    staticComponents: {
        Col: typeof GridCol;
    };
}>;
