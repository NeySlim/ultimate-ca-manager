import { BoxProps, ElementProps, Factory, StylesApiProps } from '../../core';
import { ComboboxLikeProps, ComboboxLikeRenderOptionInput, ComboboxLikeStylesNames, ComboboxStringData, ComboboxStringItem } from '../Combobox';
import { __BaseInputProps, __InputStylesNames, InputClearButtonProps, InputVariant } from '../Input';
import { ScrollAreaProps } from '../ScrollArea';
export type AutocompleteStylesNames = __InputStylesNames | ComboboxLikeStylesNames;
export interface AutocompleteProps extends BoxProps, __BaseInputProps, Omit<ComboboxLikeProps, 'data'>, StylesApiProps<AutocompleteFactory>, ElementProps<'input', 'onChange' | 'size'> {
    /** Data displayed in the dropdown. Values must be unique, otherwise an error will be thrown and component will not render. */
    data?: ComboboxStringData;
    /** Controlled component value */
    value?: string;
    /** Uncontrolled component default value */
    defaultValue?: string;
    /** Called when value changes */
    onChange?: (value: string) => void;
    /** A function to render content of the option, replaces the default content of the option */
    renderOption?: (input: ComboboxLikeRenderOptionInput<ComboboxStringItem>) => React.ReactNode;
    /** Props passed down to the underlying `ScrollArea` component in the dropdown */
    scrollAreaProps?: ScrollAreaProps;
    /** Called when the clear button is clicked */
    onClear?: () => void;
    /** Props passed down to the clear button */
    clearButtonProps?: InputClearButtonProps & ElementProps<'button'>;
    /** Determines whether the clear button should be displayed in the right section when the component has value, `false` by default */
    clearable?: boolean;
}
export type AutocompleteFactory = Factory<{
    props: AutocompleteProps;
    ref: HTMLInputElement;
    stylesNames: AutocompleteStylesNames;
    variant: InputVariant;
}>;
export declare const Autocomplete: import("../../core").MantineComponent<{
    props: AutocompleteProps;
    ref: HTMLInputElement;
    stylesNames: AutocompleteStylesNames;
    variant: InputVariant;
}>;
