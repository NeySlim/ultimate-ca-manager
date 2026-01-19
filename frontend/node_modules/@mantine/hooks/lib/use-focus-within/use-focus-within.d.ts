export interface UseFocusWithinOptions {
    onFocus?: (event: FocusEvent) => void;
    onBlur?: (event: FocusEvent) => void;
}
export declare function useFocusWithin<T extends HTMLElement = any>({ onBlur, onFocus, }?: UseFocusWithinOptions): {
    ref: React.RefObject<T>;
    focused: boolean;
};
