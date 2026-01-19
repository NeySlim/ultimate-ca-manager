export declare function useIntersection<T extends HTMLElement = any>(options?: ConstructorParameters<typeof IntersectionObserver>[1]): {
    ref: (element: T | null) => void;
    entry: IntersectionObserverEntry | null;
};
