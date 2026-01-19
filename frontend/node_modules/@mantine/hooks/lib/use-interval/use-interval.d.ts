interface UseIntervalOptions {
    /** If set, the interval will start automatically when the component is mounted, `false` by default */
    autoInvoke?: boolean;
}
export declare function useInterval(fn: () => void, interval: number, { autoInvoke }?: UseIntervalOptions): {
    start: () => void;
    stop: () => void;
    toggle: () => void;
    active: boolean;
};
export {};
