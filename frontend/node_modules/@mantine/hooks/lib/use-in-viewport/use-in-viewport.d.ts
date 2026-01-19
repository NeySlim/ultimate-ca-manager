export declare function useInViewport<T extends HTMLElement = any>(): {
    ref: (node: T | null) => void;
    inViewport: boolean;
};
