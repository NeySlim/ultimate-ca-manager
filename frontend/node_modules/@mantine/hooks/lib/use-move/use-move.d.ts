export interface UseMovePosition {
    x: number;
    y: number;
}
export declare function clampUseMovePosition(position: UseMovePosition): {
    x: number;
    y: number;
};
interface useMoveHandlers {
    onScrubStart?: () => void;
    onScrubEnd?: () => void;
}
export declare function useMove<T extends HTMLElement = any>(onChange: (value: UseMovePosition) => void, handlers?: useMoveHandlers, dir?: 'ltr' | 'rtl'): {
    ref: import("react").RefObject<T | null>;
    active: boolean;
};
export {};
