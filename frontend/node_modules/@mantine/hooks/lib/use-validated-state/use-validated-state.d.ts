export declare function useValidatedState<T>(initialValue: T, validation: (value: T) => boolean, initialValidationState?: boolean): readonly [{
    readonly value: T;
    readonly lastValidValue: T | undefined;
    readonly valid: boolean;
}, (val: T) => void];
