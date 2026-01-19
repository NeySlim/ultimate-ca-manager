import { BoxProps, ElementProps, Factory, MantineSize, StylesApiProps } from '../../core';
export type ContainerStylesNames = 'root';
export type ContainerCssVariables = {
    root: '--container-size';
};
export interface ContainerProps extends BoxProps, StylesApiProps<ContainerFactory>, ElementProps<'div'> {
    /** Sets `max-width` of the container, value is not responsive – it is the same for all screen sizes. Numbers are converted to rem. Ignored when `fluid` prop is set. `'md'` by default */
    size?: MantineSize | (string & {}) | number;
    /** Determines whether the container should take 100% of its parent width. If set, `size` prop is ignored. `false` by default. */
    fluid?: boolean;
}
export type ContainerFactory = Factory<{
    props: ContainerProps;
    ref: HTMLDivElement;
    stylesNames: ContainerStylesNames;
    vars: ContainerCssVariables;
}>;
export declare const Container: import("../../core").MantineComponent<{
    props: ContainerProps;
    ref: HTMLDivElement;
    stylesNames: ContainerStylesNames;
    vars: ContainerCssVariables;
}>;
