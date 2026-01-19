export interface ComboboxHiddenInputProps extends Omit<React.ComponentPropsWithoutRef<'input'>, 'value'> {
    /** Input value */
    value: string | string[] | null;
    /** Divider character that is used to transform array values to string, `','` by default */
    valuesDivider?: string;
}
export declare function ComboboxHiddenInput({ value, valuesDivider, ...others }: ComboboxHiddenInputProps): import("react/jsx-runtime").JSX.Element;
export declare namespace ComboboxHiddenInput {
    var displayName: string;
}
