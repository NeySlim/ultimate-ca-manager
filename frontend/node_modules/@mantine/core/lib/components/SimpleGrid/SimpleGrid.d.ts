import { BoxProps, ElementProps, Factory, MantineSpacing, StyleProp, StylesApiProps } from '../../core';
export type SimpleGridStylesNames = 'root' | 'container';
export interface SimpleGridProps extends BoxProps, StylesApiProps<SimpleGridFactory>, ElementProps<'div'> {
    /** Number of columns, `1` by default */
    cols?: StyleProp<number>;
    /** Spacing between columns, `'md'` by default */
    spacing?: StyleProp<MantineSpacing>;
    /** Spacing between rows, `'md'` by default */
    verticalSpacing?: StyleProp<MantineSpacing>;
    /** Determines typeof of queries that are used for responsive styles, `'media'` by default */
    type?: 'media' | 'container';
}
export type SimpleGridFactory = Factory<{
    props: SimpleGridProps;
    ref: HTMLDivElement;
    stylesNames: SimpleGridStylesNames;
}>;
export declare const SimpleGrid: import("../../core").MantineComponent<{
    props: SimpleGridProps;
    ref: HTMLDivElement;
    stylesNames: SimpleGridStylesNames;
}>;
