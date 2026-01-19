import { BoxProps, ElementProps, Factory, MantineColor, MantineRadius, StylesApiProps } from '../../core';
import { TimelineItem, TimelineItemStylesNames } from './TimelineItem/TimelineItem';
export type TimelineStylesNames = 'root' | TimelineItemStylesNames;
export type TimelineCssVariables = {
    root: '--tl-line-width' | '--tl-bullet-size' | '--tl-color' | '--tl-icon-color' | '--tl-radius';
};
export interface TimelineProps extends BoxProps, StylesApiProps<TimelineFactory>, ElementProps<'div'> {
    /** `Timeline.Item` components */
    children?: React.ReactNode;
    /** Index of active element */
    active?: number;
    /** Key of `theme.colors` or any valid CSS color to control active item colors, `theme.primaryColor` by default */
    color?: MantineColor;
    /** Key of `theme.radius` or any valid CSS value to set `border-radius`, numbers are converted to rem, `'xl'` by default */
    radius?: MantineRadius;
    /** Controls size of the bullet, `20` by default */
    bulletSize?: number | string;
    /** Controls how the content is positioned relative to the bullet, `'left'` by default */
    align?: 'right' | 'left';
    /** Control width of the line */
    lineWidth?: number | string;
    /** Determines whether the active items direction should be reversed without reversing items order, `false` by default */
    reverseActive?: boolean;
    /** Determines whether icon color should depend on `background-color`. If luminosity of the `color` prop is less than `theme.luminosityThreshold`, then `theme.white` will be used for text color, otherwise `theme.black`. Overrides `theme.autoContrast`. */
    autoContrast?: boolean;
}
export type TimelineFactory = Factory<{
    props: TimelineProps;
    ref: HTMLDivElement;
    stylesNames: TimelineStylesNames;
    vars: TimelineCssVariables;
    staticComponents: {
        Item: typeof TimelineItem;
    };
}>;
export declare const Timeline: import("../../core").MantineComponent<{
    props: TimelineProps;
    ref: HTMLDivElement;
    stylesNames: TimelineStylesNames;
    vars: TimelineCssVariables;
    staticComponents: {
        Item: typeof TimelineItem;
    };
}>;
