import { BoxProps, ElementProps, Factory, MantineSize, StylesApiProps } from '../../core';
export type KbdStylesNames = 'root';
export type KbdCssVariables = {
    root: '--kbd-padding' | '--kbd-fz';
};
export interface KbdProps extends BoxProps, StylesApiProps<KbdFactory>, ElementProps<'kbd'> {
    /** Controls font-size and padding, `'sm'` by default */
    size?: MantineSize | (string & {});
}
export type KbdFactory = Factory<{
    props: KbdProps;
    ref: HTMLElement;
    stylesNames: KbdStylesNames;
    vars: KbdCssVariables;
}>;
export declare const Kbd: import("../../core").MantineComponent<{
    props: KbdProps;
    ref: HTMLElement;
    stylesNames: KbdStylesNames;
    vars: KbdCssVariables;
}>;
