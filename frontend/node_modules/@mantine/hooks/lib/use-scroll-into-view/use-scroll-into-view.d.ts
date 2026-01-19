interface ScrollIntoViewAnimation {
    /** Target element alignment relatively to parent based on current axis */
    alignment?: 'start' | 'end' | 'center';
}
interface ScrollIntoViewParams {
    /** Callback fired after scroll */
    onScrollFinish?: () => void;
    /** Duration of scroll in milliseconds */
    duration?: number;
    /** Axis of scroll */
    axis?: 'x' | 'y';
    /** Custom mathematical easing function */
    easing?: (t: number) => number;
    /** Additional distance between nearest edge and element */
    offset?: number;
    /** Indicator if animation may be interrupted by user scrolling */
    cancelable?: boolean;
    /** Prevents content jumping in scrolling lists with multiple targets */
    isList?: boolean;
}
interface ScrollIntoViewReturnType<Target extends HTMLElement = any, Parent extends HTMLElement | null = null> {
    scrollableRef: React.RefObject<Parent>;
    targetRef: React.RefObject<Target>;
    scrollIntoView: (params?: ScrollIntoViewAnimation) => void;
    cancel: () => void;
}
export declare function useScrollIntoView<Target extends HTMLElement = any, Parent extends HTMLElement | null = null>({ duration, axis, onScrollFinish, easing, offset, cancelable, isList, }?: ScrollIntoViewParams): ScrollIntoViewReturnType<Target, Parent>;
export {};
