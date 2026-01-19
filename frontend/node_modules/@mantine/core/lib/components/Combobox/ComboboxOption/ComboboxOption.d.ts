import { BoxProps, CompoundStylesApiProps, ElementProps, Factory } from '../../../core';
export type ComboboxOptionStylesNames = 'option';
export interface ComboboxOptionProps extends BoxProps, CompoundStylesApiProps<ComboboxOptionFactory>, ElementProps<'div'> {
    /** Option value */
    value: string;
    /** Determines whether the option is selected */
    active?: boolean;
    /** Determines whether the option can be selected */
    disabled?: boolean;
    /** Determines whether item is selected, useful for virtualized comboboxes */
    selected?: boolean;
}
export type ComboboxOptionFactory = Factory<{
    props: ComboboxOptionProps;
    ref: HTMLDivElement;
    stylesNames: ComboboxOptionStylesNames;
    compound: true;
}>;
export declare const ComboboxOption: import("../../../core").MantineComponent<{
    props: ComboboxOptionProps;
    ref: HTMLDivElement;
    stylesNames: ComboboxOptionStylesNames;
    compound: true;
}>;
