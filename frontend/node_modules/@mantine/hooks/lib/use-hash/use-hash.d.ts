interface UseHashOptions {
    getInitialValueInEffect?: boolean;
}
export declare function useHash({ getInitialValueInEffect }?: UseHashOptions): readonly [string, (value: string) => void];
export {};
