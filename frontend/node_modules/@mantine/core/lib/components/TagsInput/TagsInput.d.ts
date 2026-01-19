import { BoxProps, ElementProps, Factory, StylesApiProps } from '../../core';
import { ComboboxLikeProps, ComboboxLikeRenderOptionInput, ComboboxLikeStylesNames, ComboboxStringData, ComboboxStringItem } from '../Combobox';
import { __BaseInputProps, __InputStylesNames, InputClearButtonProps } from '../Input';
import { ScrollAreaProps } from '../ScrollArea';
export type TagsInputStylesNames = __InputStylesNames | ComboboxLikeStylesNames | 'pill' | 'pillsList' | 'inputField';
export interface TagsInputProps extends BoxProps, __BaseInputProps, Omit<ComboboxLikeProps, 'data'>, StylesApiProps<TagsInputFactory>, ElementProps<'input', 'size' | 'value' | 'defaultValue' | 'onChange'> {
    /** Data displayed in the dropdown. Values must be unique, otherwise an error will be thrown and component will not render. */
    data?: ComboboxStringData;
    /** Controlled component value */
    value?: string[];
    /** Default value for uncontrolled component */
    defaultValue?: string[];
    /** Called when value changes */
    onChange?: (value: string[]) => void;
    /** Called when tag is removed */
    onRemove?: (value: string) => void;
    /** Called when the clear button is clicked */
    onClear?: () => void;
    /** Controlled search value */
    searchValue?: string;
    /** Default search value */
    defaultSearchValue?: string;
    /** Called when search changes */
    onSearchChange?: (value: string) => void;
    /** Maximum number of tags, `Infinity` by default */
    maxTags?: number;
    /** Determines whether duplicate tags are allowed, `false` by default */
    allowDuplicates?: boolean;
    /** Called when user tries to submit a duplicated tag */
    onDuplicate?: (value: string) => void;
    /** Characters that should trigger tags split, `[',']` by default */
    splitChars?: string[];
    /** Determines whether the clear button should be displayed in the right section when the component has value, `false` by default */
    clearable?: boolean;
    /** Props passed down to the clear button */
    clearButtonProps?: InputClearButtonProps & ElementProps<'button'>;
    /** Props passed down to the hidden input */
    hiddenInputProps?: Omit<React.ComponentPropsWithoutRef<'input'>, 'value'>;
    /** Divider used to separate values in the hidden input `value` attribute, `','` by default */
    hiddenInputValuesDivider?: string;
    /** A function to render content of the option, replaces the default content of the option */
    renderOption?: (input: ComboboxLikeRenderOptionInput<ComboboxStringItem>) => React.ReactNode;
    /** Props passed down to the underlying `ScrollArea` component in the dropdown */
    scrollAreaProps?: ScrollAreaProps;
    /** Determines whether the value typed in by the user but not submitted should be accepted when the input is blurred, `true` by default */
    acceptValueOnBlur?: boolean;
}
export type TagsInputFactory = Factory<{
    props: TagsInputProps;
    ref: HTMLInputElement;
    stylesNames: TagsInputStylesNames;
}>;
export declare const TagsInput: import("../../core").MantineComponent<{
    props: TagsInputProps;
    ref: HTMLInputElement;
    stylesNames: TagsInputStylesNames;
}>;
