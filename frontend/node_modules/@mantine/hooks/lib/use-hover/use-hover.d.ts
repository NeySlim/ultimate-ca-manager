export declare function useHover<T extends HTMLElement = any>(): {
    ref: import("react").RefObject<T | null>;
    hovered: boolean;
};
