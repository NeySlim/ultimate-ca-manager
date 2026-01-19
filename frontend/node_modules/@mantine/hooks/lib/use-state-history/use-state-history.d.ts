export interface UseStateHistoryHandlers<T> {
    set: (value: T) => void;
    back: (steps?: number) => void;
    forward: (steps?: number) => void;
    reset: () => void;
}
export interface StateHistory<T> {
    history: T[];
    current: number;
}
export declare function useStateHistory<T>(initialValue: T): [T, UseStateHistoryHandlers<T>, StateHistory<T>];
