export declare function useDebouncedValue<T = any>(value: T, wait: number, options?: {
    leading: boolean;
}): readonly [T, () => void];
