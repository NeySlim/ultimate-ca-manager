import { BoxProps, ElementProps, Factory, MantineRadius, StylesApiProps } from '../../../core';
export type RadioCardStylesNames = 'card';
export type RadioCardCssVariables = {
    card: '--card-radius';
};
export interface RadioCardProps extends BoxProps, StylesApiProps<RadioCardFactory>, ElementProps<'button', 'onChange'> {
    /** Checked state */
    checked?: boolean;
    /** Determines whether the card should have border, `true` by default */
    withBorder?: boolean;
    /** Key of `theme.radius` or any valid CSS value to set `border-radius`, numbers are converted to rem, `theme.defaultRadius` by default */
    radius?: MantineRadius;
    /** Value of the checkbox, used with `Radio.Group` */
    value?: string;
    /** Value used to associate all related radio cards, required for accessibility if used outside of `Radio.Group` */
    name?: string;
}
export type RadioCardFactory = Factory<{
    props: RadioCardProps;
    ref: HTMLButtonElement;
    stylesNames: RadioCardStylesNames;
    vars: RadioCardCssVariables;
}>;
export declare const RadioCard: import("../../../core").MantineComponent<{
    props: RadioCardProps;
    ref: HTMLButtonElement;
    stylesNames: RadioCardStylesNames;
    vars: RadioCardCssVariables;
}>;
