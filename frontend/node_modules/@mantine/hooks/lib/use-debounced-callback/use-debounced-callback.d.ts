export declare function useDebouncedCallback<T extends (...args: any[]) => any>(callback: T, options: number | {
    delay: number;
    flushOnUnmount?: boolean;
}): ((...args: Parameters<T>) => void) & {
    flush: () => void;
};
