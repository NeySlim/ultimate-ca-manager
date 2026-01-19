import { BoxProps, ElementProps, Factory, MantineColor, StylesApiProps } from '../../core';
import { ComboboxItem, ComboboxLikeProps, ComboboxLikeRenderOptionInput, ComboboxLikeStylesNames } from '../Combobox';
import { __BaseInputProps, __InputStylesNames, InputClearButtonProps, InputVariant } from '../Input';
import { ScrollAreaProps } from '../ScrollArea';
export type SelectStylesNames = __InputStylesNames | ComboboxLikeStylesNames;
export interface SelectProps extends BoxProps, __BaseInputProps, ComboboxLikeProps, StylesApiProps<SelectFactory>, ElementProps<'input', 'onChange' | 'size' | 'value' | 'defaultValue'> {
    /** Controlled component value */
    value?: string | null;
    /** Uncontrolled component default value */
    defaultValue?: string | null;
    /** Called when value changes */
    onChange?: (value: string | null, option: ComboboxItem) => void;
    /** Called when the clear button is clicked */
    onClear?: () => void;
    /** Determines whether the select should be searchable, `false` by default */
    searchable?: boolean;
    /** Determines whether check icon should be displayed near the selected option label, `true` by default */
    withCheckIcon?: boolean;
    /** Position of the check icon relative to the option label, `'left'` by default */
    checkIconPosition?: 'left' | 'right';
    /** Message displayed when no option matches the current search query while the `searchable` prop is set or there is no data */
    nothingFoundMessage?: React.ReactNode;
    /** Controlled search value */
    searchValue?: string;
    /** Default search value */
    defaultSearchValue?: string;
    /** Called when search changes */
    onSearchChange?: (value: string) => void;
    /** Determines whether it should be possible to deselect value by clicking on the selected option, `true` by default */
    allowDeselect?: boolean;
    /** Determines whether the clear button should be displayed in the right section when the component has value, `false` by default */
    clearable?: boolean;
    /** Props passed down to the clear button */
    clearButtonProps?: InputClearButtonProps & ElementProps<'button'>;
    /** Props passed down to the hidden input */
    hiddenInputProps?: Omit<React.ComponentPropsWithoutRef<'input'>, 'value'>;
    /** A function to render content of the option, replaces the default content of the option */
    renderOption?: (item: ComboboxLikeRenderOptionInput<ComboboxItem>) => React.ReactNode;
    /** Props passed down to the underlying `ScrollArea` component in the dropdown */
    scrollAreaProps?: ScrollAreaProps;
    /** Controls color of the default chevron, by default depends on the color scheme */
    chevronColor?: MantineColor;
}
export type SelectFactory = Factory<{
    props: SelectProps;
    ref: HTMLInputElement;
    stylesNames: SelectStylesNames;
    variant: InputVariant;
}>;
export declare const Select: import("../../core").MantineComponent<{
    props: SelectProps;
    ref: HTMLInputElement;
    stylesNames: SelectStylesNames;
    variant: InputVariant;
}>;
