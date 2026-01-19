import { BoxProps, ElementProps, Factory, StylesApiProps } from '../../core';
export type ScrollAreaStylesNames = 'root' | 'viewport' | 'scrollbar' | 'thumb' | 'corner';
export type ScrollAreaCssVariables = {
    root: '--scrollarea-scrollbar-size';
};
export interface ScrollAreaProps extends BoxProps, StylesApiProps<ScrollAreaFactory>, ElementProps<'div'> {
    /** Scrollbar size, any valid CSS value for width/height, numbers are converted to rem, default value is 0.75rem */
    scrollbarSize?: number | string;
    /**
     * Defines scrollbars behavior, `hover` by default
     * - `hover` – scrollbars are visible when mouse is over the scroll area
     * - `scroll` – scrollbars are visible when the scroll area is scrolled
     * - `always` – scrollbars are always visible
     * - `never` – scrollbars are always hidden
     * - `auto` – similar to `overflow: auto` – scrollbars are always visible when the content is overflowing
     * */
    type?: 'auto' | 'always' | 'scroll' | 'hover' | 'never';
    /** Scroll hide delay in ms, applicable only when type is set to `hover` or `scroll`, `1000` by default */
    scrollHideDelay?: number;
    /** Axis at which scrollbars must be rendered, `'xy'` by default */
    scrollbars?: 'x' | 'y' | 'xy' | false;
    /** Determines whether scrollbars should be offset with padding on given axis, `false` by default */
    offsetScrollbars?: boolean | 'x' | 'y' | 'present';
    /** Assigns viewport element (scrollable container) ref */
    viewportRef?: React.ForwardedRef<HTMLDivElement>;
    /** Props passed down to the viewport element */
    viewportProps?: React.ComponentPropsWithRef<'div'>;
    /** Called with current position (`x` and `y` coordinates) when viewport is scrolled */
    onScrollPositionChange?: (position: {
        x: number;
        y: number;
    }) => void;
    /** Called when scrollarea is scrolled all the way to the bottom */
    onBottomReached?: () => void;
    /** Called when scrollarea is scrolled all the way to the top */
    onTopReached?: () => void;
    /** Defines `overscroll-behavior` of the viewport */
    overscrollBehavior?: React.CSSProperties['overscrollBehavior'];
}
export interface ScrollAreaAutosizeProps extends ScrollAreaProps {
}
export type ScrollAreaFactory = Factory<{
    props: ScrollAreaProps;
    ref: HTMLDivElement;
    stylesNames: ScrollAreaStylesNames;
    vars: ScrollAreaCssVariables;
    staticComponents: {
        Autosize: typeof ScrollAreaAutosize;
    };
}>;
export declare const ScrollArea: import("../../core").MantineComponent<{
    props: ScrollAreaProps;
    ref: HTMLDivElement;
    stylesNames: ScrollAreaStylesNames;
    vars: ScrollAreaCssVariables;
    staticComponents: {
        Autosize: typeof ScrollAreaAutosize;
    };
}>;
export declare const ScrollAreaAutosize: import("../../core").MantineComponent<{
    props: ScrollAreaProps;
    ref: HTMLDivElement;
    stylesNames: ScrollAreaStylesNames;
    vars: ScrollAreaCssVariables;
    staticComponents: {
        Autosize: typeof ScrollAreaAutosize;
    };
}>;
