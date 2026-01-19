import { BoxProps, ElementProps, Factory, MantineColor, StylesApiProps } from '../../core';
import { ComboboxItem, ComboboxLikeProps, ComboboxLikeRenderOptionInput, ComboboxLikeStylesNames } from '../Combobox';
import { __BaseInputProps, __InputStylesNames, InputClearButtonProps } from '../Input';
import { ScrollAreaProps } from '../ScrollArea';
export type MultiSelectStylesNames = __InputStylesNames | ComboboxLikeStylesNames | 'pill' | 'pillsList' | 'inputField';
export interface MultiSelectProps extends BoxProps, __BaseInputProps, ComboboxLikeProps, StylesApiProps<MultiSelectFactory>, ElementProps<'input', 'size' | 'value' | 'defaultValue' | 'onChange'> {
    /** Controlled component value */
    value?: string[];
    /** Default value for uncontrolled component */
    defaultValue?: string[];
    /** Called when value changes */
    onChange?: (value: string[]) => void;
    /** Called with `value` of the removed item */
    onRemove?: (value: string) => void;
    /** Called when the clear button is clicked */
    onClear?: () => void;
    /** Controlled search value */
    searchValue?: string;
    /** Default search value */
    defaultSearchValue?: string;
    /** Called when search changes */
    onSearchChange?: (value: string) => void;
    /** Maximum number of values, `Infinity` by default */
    maxValues?: number;
    /** Determines whether the select should be searchable, `false` by default */
    searchable?: boolean;
    /** Message displayed when no option matches the current search query while the `searchable` prop is set or there is no data */
    nothingFoundMessage?: React.ReactNode;
    /** Determines whether check icon should be displayed near the selected option label, `true` by default */
    withCheckIcon?: boolean;
    /** Position of the check icon relative to the option label, `'left'` by default */
    checkIconPosition?: 'left' | 'right';
    /** Determines whether picked options should be removed from the options list, `false` by default */
    hidePickedOptions?: boolean;
    /** Determines whether the clear button should be displayed in the right section when the component has value, `false` by default */
    clearable?: boolean;
    /** Props passed down to the clear button */
    clearButtonProps?: InputClearButtonProps & ElementProps<'button'>;
    /** Props passed down to the hidden input */
    hiddenInputProps?: Omit<React.ComponentPropsWithoutRef<'input'>, 'value'>;
    /** Divider used to separate values in the hidden input `value` attribute, `','` by default */
    hiddenInputValuesDivider?: string;
    /** A function to render content of the option, replaces the default content of the option */
    renderOption?: (item: ComboboxLikeRenderOptionInput<ComboboxItem>) => React.ReactNode;
    /** Props passed down to the underlying `ScrollArea` component in the dropdown */
    scrollAreaProps?: ScrollAreaProps;
    /** Controls color of the default chevron, by default depends on the color scheme */
    chevronColor?: MantineColor;
}
export type MultiSelectFactory = Factory<{
    props: MultiSelectProps;
    ref: HTMLInputElement;
    stylesNames: MultiSelectStylesNames;
}>;
export declare const MultiSelect: import("../../core").MantineComponent<{
    props: MultiSelectProps;
    ref: HTMLInputElement;
    stylesNames: MultiSelectStylesNames;
}>;
