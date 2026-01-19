export declare const isFixed: (current: number, fixedAt: number) => boolean;
export declare const isPinned: (current: number, previous: number) => boolean;
export declare const isReleased: (current: number, previous: number, fixedAt: number) => boolean;
export declare const isPinnedOrReleased: (current: number, fixedAt: number, isCurrentlyPinnedRef: React.MutableRefObject<boolean>, isScrollingUp: boolean, onPin?: () => void, onRelease?: () => void) => void;
export declare const useScrollDirection: () => boolean;
interface UseHeadroomInput {
    /** Number in px at which element should be fixed */
    fixedAt?: number;
    /** Called when element is pinned */
    onPin?: () => void;
    /** Called when element is at fixed position */
    onFix?: () => void;
    /** Called when element is unpinned */
    onRelease?: () => void;
}
export declare function useHeadroom({ fixedAt, onPin, onFix, onRelease }?: UseHeadroomInput): boolean;
export {};
