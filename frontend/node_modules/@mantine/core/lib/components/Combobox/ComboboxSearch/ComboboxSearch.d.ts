import { ElementProps, Factory } from '../../../core';
import { InputProps, InputStylesNames } from '../../Input/Input';
export type ComboboxSearchStylesNames = InputStylesNames;
export interface ComboboxSearchProps extends InputProps, ElementProps<'input', 'size'> {
    /** Determines whether the search input should have `aria-` attribute, `true` by default */
    withAriaAttributes?: boolean;
    /** Determines whether the search input should handle keyboard navigation, `true` by default */
    withKeyboardNavigation?: boolean;
}
export type ComboboxSearchFactory = Factory<{
    props: ComboboxSearchProps;
    ref: HTMLInputElement;
    stylesNames: ComboboxSearchStylesNames;
}>;
export declare const ComboboxSearch: import("../../../core").MantineComponent<{
    props: ComboboxSearchProps;
    ref: HTMLInputElement;
    stylesNames: ComboboxSearchStylesNames;
}>;
