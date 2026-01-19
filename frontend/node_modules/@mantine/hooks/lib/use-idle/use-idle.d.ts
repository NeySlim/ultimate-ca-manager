export declare function useIdle(timeout: number, options?: Partial<{
    events: (keyof DocumentEventMap)[];
    initialState: boolean;
}>): boolean;
