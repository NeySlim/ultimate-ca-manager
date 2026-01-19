import { BoxProps, ElementProps, Factory, MantineFontSize, StylesApiProps } from '../../../core';
export type InputLabelStylesNames = 'label' | 'required';
export type InputLabelCssVariables = {
    label: '--input-asterisk-color' | '--input-label-size';
};
export interface InputLabelProps extends BoxProps, StylesApiProps<InputLabelFactory>, ElementProps<'label'> {
    __staticSelector?: string;
    /** Determines whether the required asterisk should be displayed  */
    required?: boolean;
    /** Controls label `font-size`, `'sm'` by default */
    size?: MantineFontSize;
    /** Root element of the label, `'label'` by default */
    labelElement?: 'label' | 'div';
}
export type InputLabelFactory = Factory<{
    props: InputLabelProps;
    ref: HTMLLabelElement;
    stylesNames: InputLabelStylesNames;
    vars: InputLabelCssVariables;
}>;
export declare const InputLabel: import("../../../core").MantineComponent<{
    props: InputLabelProps;
    ref: HTMLLabelElement;
    stylesNames: InputLabelStylesNames;
    vars: InputLabelCssVariables;
}>;
