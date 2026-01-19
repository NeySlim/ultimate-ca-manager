import { BoxProps, CompoundStylesApiProps, ElementProps, Factory, MantineColor, MantineRadius } from '../../../core';
export type TimelineItemStylesNames = 'itemBody' | 'itemContent' | 'itemBullet' | 'item' | 'itemTitle';
export interface TimelineItemProps extends BoxProps, CompoundStylesApiProps<TimelineItemFactory>, ElementProps<'div', 'title'> {
    /** Determines whether the item should be highlighted, controlled by the parent `Timeline` component  */
    __active?: boolean;
    /** Determines whether the line of the item should be highlighted, controlled by the parent Timeline component */
    __lineActive?: boolean;
    /** Line and bullet position relative to item content, controlled by the parent Timeline component */
    __align?: 'right' | 'left';
    /** Item title, displayed next to the bullet */
    title?: React.ReactNode;
    /** Content displayed below the title */
    children?: React.ReactNode;
    /** React node that should be rendered inside the bullet – icon, image, avatar, etc. By default, large white dot is displayed. */
    bullet?: React.ReactNode;
    /** Key of `theme.radius` or any valid CSS value to set `border-radius`, numbers are converted to rem, `'xl'` by default */
    radius?: MantineRadius;
    /** Key of `theme.colors` or any valid CSS color to control active item colors, `theme.primaryColor` by default */
    color?: MantineColor;
    /** Controls line border style, `'solid'` by default */
    lineVariant?: 'solid' | 'dashed' | 'dotted';
}
export type TimelineItemFactory = Factory<{
    props: TimelineItemProps;
    ref: HTMLDivElement;
    stylesNames: TimelineItemStylesNames;
    compound: true;
}>;
export declare const TimelineItem: import("../../../core").MantineComponent<{
    props: TimelineItemProps;
    ref: HTMLDivElement;
    stylesNames: TimelineItemStylesNames;
    compound: true;
}>;
