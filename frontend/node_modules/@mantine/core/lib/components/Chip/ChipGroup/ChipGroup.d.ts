export interface ChipGroupProps<T extends boolean = false> {
    /** Determines whether it is allowed to select multiple values, `false` by default */
    multiple?: T;
    /** Controlled component value */
    value?: T extends true ? string[] : string | null;
    /** Uncontrolled component initial value */
    defaultValue?: T extends true ? string[] : string | null;
    /** Called when value changes. If `multiple` prop is set, called with an array of selected values. If not, called with a string value of selected chip. */
    onChange?: (value: T extends true ? string[] : string) => void;
    /** `Chip` components and any other elements */
    children?: React.ReactNode;
}
export declare function ChipGroup<T extends boolean>(props: ChipGroupProps<T>): import("react/jsx-runtime").JSX.Element;
export declare namespace ChipGroup {
    var displayName: string;
}
