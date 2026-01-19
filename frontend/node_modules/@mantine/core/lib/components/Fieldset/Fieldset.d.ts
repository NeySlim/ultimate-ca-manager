import { BoxProps, ElementProps, Factory, MantineRadius, StylesApiProps } from '../../core';
export type FieldsetStylesNames = 'root' | 'legend';
export type FieldsetVariant = 'default' | 'filled' | 'unstyled';
export type FieldsetCSSVariables = {
    root: '--fieldset-radius';
};
export interface FieldsetProps extends BoxProps, StylesApiProps<FieldsetFactory>, ElementProps<'fieldset'> {
    /** Fieldset legend */
    legend?: React.ReactNode;
    /** Key of `theme.radius` or any valid CSS value to set `border-radius`, `theme.defaultRadius` by default */
    radius?: MantineRadius;
}
export type FieldsetFactory = Factory<{
    props: FieldsetProps;
    ref: HTMLFieldSetElement;
    stylesNames: FieldsetStylesNames;
    vars: FieldsetCSSVariables;
    variant: FieldsetVariant;
}>;
export declare const Fieldset: import("../../core").MantineComponent<{
    props: FieldsetProps;
    ref: HTMLFieldSetElement;
    stylesNames: FieldsetStylesNames;
    vars: FieldsetCSSVariables;
    variant: FieldsetVariant;
}>;
