import { MantineTransition } from './transitions';
export interface TransitionProps {
    /** If set element will not be unmounted from the DOM when it is hidden, `display: none` styles will be applied instead */
    keepMounted?: boolean;
    /** Transition name or object */
    transition?: MantineTransition;
    /** Transition duration in ms, `250` by default */
    duration?: number;
    /** Exit transition duration in ms, `250` by default */
    exitDuration?: number;
    /** Transition timing function, `theme.transitionTimingFunction` by default */
    timingFunction?: string;
    /** Determines whether component should be mounted to the DOM */
    mounted: boolean;
    /** Render function with transition styles argument */
    children: (styles: React.CSSProperties) => React.JSX.Element;
    /** Called when exit transition ends */
    onExited?: () => void;
    /** Called when exit transition starts */
    onExit?: () => void;
    /** Called when enter transition starts */
    onEnter?: () => void;
    /** Called when enter transition ends */
    onEntered?: () => void;
    /** Delay in ms before enter transition starts */
    enterDelay?: number;
    /** Delay in ms before exit transition starts */
    exitDelay?: number;
}
export type TransitionOverride = Partial<Omit<TransitionProps, 'mounted'>>;
export declare function Transition({ keepMounted, transition, duration, exitDuration, mounted, children, timingFunction, onExit, onEntered, onEnter, onExited, enterDelay, exitDelay, }: TransitionProps): import("react/jsx-runtime").JSX.Element | null;
export declare namespace Transition {
    var displayName: string;
}
