export declare function useSetState<T extends Record<string, any>>(initialState: T): readonly [T, (statePartial: Partial<T> | ((currentState: T) => Partial<T>)) => void];
