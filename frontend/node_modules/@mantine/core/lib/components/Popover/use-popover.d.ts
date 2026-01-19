import { FloatingAxesOffsets, FloatingPosition, FloatingStrategy } from '../Floating';
import { PopoverMiddlewares, PopoverWidth } from './Popover.types';
interface UsePopoverOptions {
    offset: number | FloatingAxesOffsets;
    position: FloatingPosition;
    positionDependencies: any[] | undefined;
    onPositionChange?: (position: FloatingPosition) => void;
    opened: boolean | undefined;
    defaultOpened: boolean | undefined;
    onChange?: (opened: boolean) => void;
    onClose?: () => void;
    onDismiss?: () => void;
    onOpen?: () => void;
    width: PopoverWidth;
    middlewares: PopoverMiddlewares | undefined;
    arrowRef: React.RefObject<HTMLDivElement | null>;
    arrowOffset: number;
    strategy?: FloatingStrategy;
    disabled: boolean | undefined;
}
export declare function usePopover(options: UsePopoverOptions): {
    floating: {
        placement: import("@floating-ui/react").Placement;
        strategy: import("@floating-ui/react").Strategy;
        middlewareData: import("@floating-ui/core").MiddlewareData;
        x: number;
        y: number;
        isPositioned: boolean;
        update: () => void;
        floatingStyles: React.CSSProperties;
        refs: {
            reference: import("react").MutableRefObject<import("@floating-ui/react-dom").ReferenceType | null>;
            floating: React.MutableRefObject<HTMLElement | null>;
            setReference: (node: import("@floating-ui/react-dom").ReferenceType | null) => void;
            setFloating: (node: HTMLElement | null) => void;
        } & import("@floating-ui/react").ExtendedRefs<Element>;
        elements: {
            reference: import("@floating-ui/react-dom").ReferenceType | null;
            floating: HTMLElement | null;
        } & import("@floating-ui/react").ExtendedElements<Element>;
        context: {
            strategy: import("@floating-ui/react").Strategy;
            placement: import("@floating-ui/react").Placement;
            x: number;
            y: number;
            middlewareData: import("@floating-ui/core").MiddlewareData;
            isPositioned: boolean;
            update: () => void;
            floatingStyles: React.CSSProperties;
            open: boolean;
            onOpenChange: (open: boolean, event?: Event, reason?: import("@floating-ui/react").OpenChangeReason) => void;
            events: import("@floating-ui/react").FloatingEvents;
            dataRef: React.MutableRefObject<import("@floating-ui/react").ContextData>;
            nodeId: string | undefined;
            floatingId: string;
            refs: import("@floating-ui/react").ExtendedRefs<Element>;
            elements: import("@floating-ui/react").ExtendedElements<Element>;
        };
    };
    controlled: boolean;
    opened: boolean;
    onClose: () => void;
    onToggle: () => false | void;
};
export {};
